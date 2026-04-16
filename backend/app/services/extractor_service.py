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
        Classifica o documento e retorna o tipo da peça (classe_documental).
        O LLM responde em JSON estruturado com macro_categoria, classe_documental,
        confidence e justificativa — usado para log/auditoria.
        Retorna a string classe_documental para manter compatibilidade.
        """
        import json as _json
        # As duas primeiras páginas são suficientes para classificação.
        # 15.000 chars ≈ 3k tokens — suficiente para cabeçalho + abertura + assinatura
        texto_curto = texto[:15000]

        prompt = SYSTEM_PROMPT_CLASSIFICADOR_PECA.format(texto=texto_curto)

        try:
            result = await self.llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="triagem",
                temperature=0.0,
                max_tokens=300,  # JSON com justificativa cabe em ~150 tokens
                json_mode=True,
                agente="Classificacao",
            )
            raw = result["content"].strip()
            dados = _json.loads(raw)
            categoria = dados.get("classe_documental", "outro").strip().lower()
            confidence = dados.get("confidence", "media")
            justificativa = dados.get("justificativa", "")
            macro = dados.get("macro_categoria", "")

            nivel = "warning" if confidence == "baixa" else "info"
            getattr(logger, nivel)(
                f"[CLASSIFICACAO] {categoria} | {macro} | confiança={confidence} | {justificativa}"
            )
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
                tier="extracao",
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
