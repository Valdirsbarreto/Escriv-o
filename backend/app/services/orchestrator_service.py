"""
Escrivão AI — Agente Orquestrador (Sprint F5)
Responsável pela inteligência da Ingestão Primária e coordenação de tarefas.
Conforme blueprint §12.3: O Agente Orquestrador.
"""

import logging
import json
import uuid
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from app.services.llm_service import LLMService
from app.core.prompts import (
    SYSTEM_PROMPT_ORQUESTRADOR,
    SYSTEM_PROMPT_GERAR_RELATORIO_INICIAL
)
from app.models.inquerito import Inquerito
from app.models.pessoa import Pessoa
from app.models.evento_cronologico import EventoCronologico

logger = logging.getLogger(__name__)

class OrchestratorService:
    """
    Serviço que usa o LLM Premium (Gemini) para orquestrar o início de um inquérito.
    """

    def __init__(self):
        self.llm_service = LLMService()

    async def analisar_documentos_iniciais(self, texto_extraido: str) -> Dict[str, Any]:
        """
        Analisa o texto dos primeiros documentos para extrair metadados do inquérito e personagens.
        """
        # Limitamos o texto para os primeiros 40k caracteres ( Gemini suporta muito mais, mas para extração focada basta)
        texto_curto = texto_extraido[:40000]

        prompt = SYSTEM_PROMPT_ORQUESTRADOR.format(texto=texto_curto)

        try:
            result = await self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="standard",
                temperature=0.1,
                max_tokens=2000,
                json_mode=True
            )
            
            content = result["content"].strip()
            # Limpeza básica se necessário
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            
            dados = json.loads(content)
            return dados
        except Exception as e:
            logger.error(f"[ORQUESTRADOR] Falha na análise inicial: {e}")
            return {}

    async def gerar_relatorio_contextualizado(self, inquerito_id: uuid.UUID, contexto: str) -> str:
        """
        Gera o relatório de boas-vindas baseado no que foi extraído.
        """
        prompt = SYSTEM_PROMPT_GERAR_RELATORIO_INICIAL.format(contexto=contexto)

        try:
            result = await self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="standard",
                temperature=0.7,
                max_tokens=1500
            )
            return result["content"].strip()
        except Exception as e:
            logger.error(f"[ORQUESTRADOR] Falha ao gerar relatório: {e}")
            return "Erro ao gerar relatório inicial."

    def salvar_personagens_e_contexto(self, db: Session, inquerito_id: uuid.UUID, personagens: List[Dict[str, Any]]):
        """
        Salva as pessoas identificadas e seus contextos iniciais.
        """
        for p_dict in personagens:
            nome = p_dict.get("nome", "Desconhecido")
            papel = p_dict.get("papel", "outro")
            contexto = p_dict.get("contexto_inicial", "")
            
            # Verificar se já existe (heurística simples por nome)
            existente = db.query(Pessoa).filter(
                Pessoa.inquerito_id == inquerito_id,
                Pessoa.nome == nome
            ).first()
            
            if not existente:
                pessoa = Pessoa(
                    inquerito_id=inquerito_id,
                    nome=nome,
                    tipo_pessoa=papel,
                    resumo_contexto=contexto
                )
                db.add(pessoa)
            else:
                # Atualiza contexto se estiver vazio
                if not existente.resumo_contexto:
                    existente.resumo_contexto = contexto
        
        db.commit()
