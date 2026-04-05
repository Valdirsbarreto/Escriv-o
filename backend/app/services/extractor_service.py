"""
Escrivão AI — Serviço Extrator (LLM Econômico)
Realiza classificação de peças e extração de entidades (NER) via chamada LLM.
Conforme blueprint §11.1 (Modelos Econômicos para tarefas repetitivas).
"""

import logging
import json
from typing import Dict, Any

from app.services.llm_service import LLMService
from app.core.prompts import (
    SYSTEM_PROMPT_CLASSIFICADOR_PECA,
    SYSTEM_PROMPT_EXTRACAO_ENTIDADES,
)

logger = logging.getLogger(__name__)


class ExtractorService:
    """
    Serviço que usa o LLM da camada Econômica para:
    - Identificar qual o tipo de documento/peça.
    - Fazer NER (Reconhecimento de Entidades Nomeadas) estruturado.
    """

    def __init__(self):
        self.llm_service = LLMService()

    async def classificar_documento(self, texto: str) -> str:
        """
        Analisa o texto de um documento e retorna o tipo da peça.
        Usa o modelo Econômico.
        """
        # Uma boa classificação normalmente usa as 2 primeiras páginas.
        # Limitaremos o texto a cerca de 15.000 caracteres (aprox 3k tokens)
        texto_curto = texto[:15000]

        prompt = SYSTEM_PROMPT_CLASSIFICADOR_PECA.format(texto=texto_curto)

        try:
            result = await self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="economico",
                temperature=0.0,  # Queremos precisão/determinismo
                max_tokens=50,
                agente="Classificacao",
            )
            categoria = result["content"].strip().lower()
            return categoria
        except Exception as e:
            logger.error(f"[EXTRATOR] Falha ao classificar documento: {e}")
            return "outro"

    async def extrair_entidades(self, texto: str) -> Dict[str, Any]:
        """
        Faz NER e retorna JSON com pessoas, empresas, enderecos, etc.
        Usa o modelo Econômico no modo JSON.
        """
        # Se for muito longo, pode falhar no limite de contexto de alguns modelos menores.
        # Limitamos a 30k chars (aprox 6-8k tokens). Documentos maiores 
        # deveriam ser passados em chunks na task (faremos em batch se preciso).
        texto_curto = texto[:30000]

        prompt = SYSTEM_PROMPT_EXTRACAO_ENTIDADES.format(texto=texto_curto)

        try:
            result = await self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="standard",
                temperature=0.1,  # Baixa temp para estruturação confiável
                max_tokens=3000,
                json_mode=True,
                agente="NER",
            )
            
            content = result["content"].strip()
            # Limpa block quote de markdown se o modelo ainda insistir (mesmo em json_mode)
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            
            dados = json.loads(content)
            
            # Garante a estrutura base
            estrutura_base = {
                "pessoas": [], "empresas": [], "enderecos": [],
                "telefones": [], "emails": [], "cronologia": []
            }
            estrutura_base.update(dados)
            return estrutura_base

        except json.JSONDecodeError as e:
            logger.error(f"[EXTRATOR] Falha ao parsear JSON do NER: {e}")
            logger.debug(f"Retorno falho: {result.get('content')}")
            return {"pessoas": [], "empresas": [], "enderecos": [], "telefones": [], "emails": [], "cronologia": []}
        except Exception as e:
            logger.error(f"[EXTRATOR] Falha na extração de entidades: {e}")
            return {"pessoas": [], "empresas": [], "enderecos": [], "telefones": [], "emails": [], "cronologia": []}
