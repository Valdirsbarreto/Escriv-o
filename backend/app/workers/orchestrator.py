"""
Escrivão AI — Agente Orquestrador (Worker)
Gerencia a criação automatizada de inquéritos a partir de documentos.
"""

import logging
import time
import uuid
import hashlib
import re
from typing import List
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.workers.celery_app import celery_app
from app.services.storage import StorageService
from app.services.pdf_extractor import PDFExtractorService
from app.services.orchestrator_service import OrchestratorService
from app.models.inquerito import Inquerito
from app.models.documento import Documento
from app.core.state_machine import EstadoInquerito

logger = logging.getLogger(__name__)
sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=1,
    max_overflow=1,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Padrões comuns de número de IP no RJ: 033-07699-2016, 033.07699/2016, 07699/2016
_IP_PATTERNS = [
    re.compile(r'(\d{3})[-.](\d{4,6})[/\-\.](\d{4})'),  # 033-07699-2016
    re.compile(r'(\d{4,6})[/\-](\d{4})'),                 # 07699/2016
]

def _normalizar_numero_ip(numero: str) -> str:
    """
    Normaliza número de IP para formato canônico DDD-NNNNN-YYYY.
    Exemplos:
      "921-332-2012"    → "921-00332-2012"
      "921/332/2012"    → "921-00332-2012"
      "921-00332-2012"  → "921-00332-2012"
      "033.07699.2016"  → "033-07699-2016"
    """
    m = re.match(r'^(\d{3})[-./](\d+)[-./](\d{4})$', numero.strip())
    if m:
        delegacia = m.group(1)
        seq = m.group(2).zfill(5)  # zero-padding a 5 dígitos
        ano = m.group(3)
        return f"{delegacia}-{seq}-{ano}"
    return numero


def _extrair_numero_ip_dos_filenames(filenames: List[str]):
    """Tenta extrair número do IP dos nomes dos arquivos antes de chamar o LLM."""
    for fname in filenames:
        nome = fname.replace('_', '-').replace(' ', '-')
        for pattern in _IP_PATTERNS:
            m = pattern.search(nome)
            if m:
                grupos = m.groups()
                if len(grupos) == 3:
                    numero = f"{grupos[0]}-{grupos[1]}-{grupos[2]}"
                    return _normalizar_numero_ip(numero), int(grupos[2])
                elif len(grupos) == 2:
                    numero = f"{grupos[0]}-{grupos[1]}"
                    return numero, int(grupos[1])
    return None, None

@celery_app.task(bind=True, max_retries=2)
def orchestrate_new_inquerito(self, storage_paths: List[str], filenames: List[str]):
    """
    Task mestre que recebe arquivos recém-upados e 'descobre' o inquérito.
    """
    logger.info(f"[ORQUESTRADOR] Iniciando orquestração para {len(storage_paths)} arquivos")
    
    try:
        with Session(sync_engine) as db:
            storage = StorageService()
            pdf_service = PDFExtractorService()
            orchestrator = OrchestratorService()

            # 1. Analisar o primeiro documento (geralmente o principal)
            primary_path = storage_paths[0]
            
            import asyncio

            async def _run_async():
                content = await storage.download_file(primary_path)
                extraction = pdf_service.extract_with_ocr(content)
                texto_inicial = extraction["texto_completo"]
                analise = await orchestrator.analisar_documentos_iniciais(texto_inicial)
                return extraction, texto_inicial, analise

            loop = asyncio.new_event_loop()
            extraction, texto_inicial, analise = loop.run_until_complete(_run_async())

            logger.info(f"[ORQUESTRADOR] Analise concluída: {analise.get('inquerito')}")

            # 3. Criar o Inquérito (ou recuperar se já existir)
            meta = analise.get("inquerito", {})
            # Prioridade: filename > LLM > TEMP
            numero_fname, ano_fname = _extrair_numero_ip_dos_filenames(filenames)
            numero_raw = numero_fname or meta.get("numero") or f"TEMP-{uuid.uuid4().hex[:6].upper()}"
            # Normaliza formato: garante DDD-NNNNN-YYYY com zero-padding
            numero_ip = _normalizar_numero_ip(numero_raw)
            # ano: prefere o extraído do filename/LLM; NÃO usa o ano atual como fallback
            # (IPs antigos teriam o ano atual erroneamente atribuído)
            ano_llm = meta.get("ano")
            ano = ano_fname or (int(ano_llm) if ano_llm and str(ano_llm).isdigit() else None)
            delegacia_cod = meta.get("delegacia_codigo")
            delegacia_nome = meta.get("delegacia_nome")

            # Buscar por número para evitar duplicidade (busca também a forma sem normalizar)
            numero_alt = numero_raw if numero_raw != numero_ip else None
            from sqlalchemy import or_
            filtro = [Inquerito.numero == numero_ip]
            if numero_alt:
                filtro.append(Inquerito.numero == numero_alt)
            inquerito = db.execute(
                select(Inquerito).where(or_(*filtro))
            ).scalar_one_or_none()

            if not inquerito:
                inquerito = Inquerito(
                    numero=numero_ip,
                    ano=ano,
                    delegacia_origem_codigo=delegacia_cod,
                    delegacia_origem_nome=delegacia_nome,
                    delegacia_atual_codigo=delegacia_cod,
                    delegacia_atual_nome=delegacia_nome,
                    descricao="",  # preenchido pela Seção 1 do Relatório Inicial após ingestão
                    estado_atual=EstadoInquerito.INDEXANDO.value
                )
                db.add(inquerito)
                db.flush()
                logger.info(f"[ORQUESTRADOR] Novo inquérito criado: {inquerito.id}")
            else:
                logger.info(f"[ORQUESTRADOR] Inquérito já existente: {inquerito.id}")
                inquerito.estado_atual = EstadoInquerito.INDEXANDO.value

            inquerito_id = inquerito.id
            db.commit() # Salvamos o inquérito imediatamente para aparecer no Dashboard

            # 4. Registrar documentos e disparar ingestão individual
            from app.workers.ingestion import ingest_document
            
            # Recarrega o inquerito para a sessão após o commit anterior
            inquerito = db.merge(inquerito)

            doc_ids = []
            for path, fname in zip(storage_paths, filenames):
                doc_hash = hashlib.sha256(fname.encode()).hexdigest()
                documento = Documento(
                    inquerito_id=inquerito_id,
                    nome_arquivo=fname,
                    hash_arquivo=doc_hash,
                    storage_path=path,
                    status_processamento="pendente"
                )
                db.add(documento)
                db.flush()
                doc_ids.append(str(documento.id))
                inquerito.total_documentos += 1

            # 5. Salvar Personagens Identificados e Gerar Relatório Inicial
            personagens = analise.get("personagens", [])
            orchestrator.salvar_personagens_e_contexto(db, inquerito_id, personagens)
            
            relatorio = loop.run_until_complete(
                orchestrator.gerar_relatorio_contextualizado(
                    inquerito_id,
                    str(analise)
                )
            )
            loop.close()
            inquerito.resumo_executivo = relatorio

            db.commit()
            # Disparar ingestão APÓS commit — evita race condition "documento não encontrado"
            for doc_id in doc_ids:
                ingest_document.delay(doc_id, str(inquerito_id))
            logger.info(f"[ORQUESTRADOR] Orquestração concluída para IP {numero_ip}")


            return {
                "status": "sucesso",
                "inquerito_id": str(inquerito_id),
                "numero": numero_ip
            }

    except Exception as e:
        logger.error(f"[ORQUESTRADOR] Erro fatal: {e}")
        raise self.retry(exc=e)
