"""
Script utilitário para corrigir inquéritos com número TEMP-XXXXXX.
Ele percorre os inquéritos no banco, busca documentos extraídos e tenta encontrar o número do IP via regex.
"""

import asyncio
import logging
import re
import uuid
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session

# Importamos os modelos do app para garantir registro no SQLAlchemy
from app.models.inquerito import Inquerito
from app.models.documento import Documento
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_temp")

# Padrões de IP (os mesmos do orchestrator.py e summary_task.py)
_IP_PATS = [
    re.compile(r'\b(\d{3})[-.](\d{4,6})[/\-\.](\d{4})\b'),
    re.compile(r'\bIP\s*[:\-]?\s*(\d{4,6})[/\-](\d{4})\b', re.IGNORECASE),
    re.compile(r'\b(\d{4,6})[/\-](\d{4})\b'),
]

async def fix_temp_inqueritos():
    # Usamos o engine síncrono para simplicidade do script de manutenção
    engine = create_engine(settings.DATABASE_URL_SYNC)
    
    with Session(engine) as db:
        # 1. Buscar inquéritos com número TEMP
        stmt = select(Inquerito).where(Inquerito.numero.like('TEMP-%'))
        res = db.execute(stmt)
        inqueritos_temp = res.scalars().all()
        
        logger.info(f"Encontrados {len(inqueritos_temp)} inquéritos com número TEMP.")
        
        for inq in inqueritos_temp:
            logger.info(f"Processando TEMP inquerito: {inq.id} (atual: {inq.numero})")
            
            # 2. Buscar documentos deste inquérito
            docs_stmt = select(Documento).where(Documento.inquerito_id == inq.id)
            docs_res = db.execute(docs_stmt)
            docs = docs_res.scalars().all()
            
            numero_encontrado = None
            ano_encontrado = None
            
            # 3. Escanear texto dos documentos
            for d in docs:
                if not d.texto_extraido:
                    continue
                
                # Pegamos os primeiros 10k caracteres (geralmente o número está no topo)
                trecho = d.texto_extraido[:10000]
                for pat in _IP_PATS:
                    m = pat.search(trecho)
                    if m:
                        grupos = m.groups()
                        if len(grupos) == 3:
                            numero_encontrado = f"{grupos[0]}-{grupos[1]}-{grupos[2]}"
                            ano_encontrado = int(grupos[2])
                        elif len(grupos) == 2:
                            numero_encontrado = f"{grupos[0]}-{grupos[1]}"
                            ano_encontrado = int(grupos[1])
                        break
                
                if numero_encontrado:
                    logger.info(f"Número encontrado no doc {d.nome_arquivo}: {numero_encontrado}")
                    break
            
            # 4. Atualizar se encontramos algo
            if numero_encontrado:
                logger.info(f"ATUALIZANDO: {inq.numero} -> {numero_encontrado}")
                inq.numero = numero_encontrado
                if not inq.ano:
                    inq.ano = ano_encontrado
                db.flush()
            else:
                logger.warning(f"Não foi possível encontrar o número real para {inq.numero} nos seus {len(docs)} documentos.")
        
        db.commit()
        logger.info("Processo concluído.")

if __name__ == "__main__":
    asyncio.run(fix_temp_inqueritos())
