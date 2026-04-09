"""
Escrivão AI — Agente: Produção Cautelar
Gera minutas de ofícios e requisições policiais usando LLM Premium.
Conforme blueprint §9.2 (Agente Cautelar).
"""

import logging
import uuid
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService
from app.services.summary_service import SummaryService
from app.core.prompts import PROMPT_CAUTELAR
from app.models.inquerito import Inquerito
from app.models.resultado_agente import ResultadoAgente

logger = logging.getLogger(__name__)

TIPOS_CAUTELAR = {
    "oficio_requisicao": "Ofício de Requisição",
    "mandado_busca": "Mandado de Busca e Apreensão",
    "interceptacao_telefonica": "Requerimento de Interceptação Telefônica",
    "quebra_sigilo_bancario": "Requerimento de Quebra de Sigilo Bancário",
    "autorizacao_prisao": "Requerimento de Prisão Preventiva",
    "oficio_generico": "Ofício",
}


class AgenteCautelar:
    """
    Gera minutas de atos processuais/cautelares com base nas instruções do delegado.
    Usa o contexto do inquérito (resumo) para fundamentação automática.
    """

    def __init__(self):
        self.llm = LLMService()
        self.summary_svc = SummaryService()

    async def gerar_cautelar(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        tipo_cautelar: str,
        instrucoes: str,
        autoridade: str = "Comissário de Polícia Civil",
    ) -> Dict[str, Any]:
        """
        Gera a minuta de um ato cautelar.

        Args:
            inquerito_id: UUID do inquérito
            tipo_cautelar: chave do tipo (ex: 'quebra_sigilo_bancario')
            instrucoes: texto livre com as instruções do delegado
            autoridade: nome/cargo da autoridade signatária

        Returns:
            dict com 'texto_gerado', 'tipo', 'inquerito'
        """
        # Buscar número do inquérito
        inq = await db.get(Inquerito, inquerito_id)
        numero_inquerito = inq.numero_procedimento if inq else str(inquerito_id)
        titulo_tipo = TIPOS_CAUTELAR.get(tipo_cautelar, tipo_cautelar)

        # Buscar resumo do caso para fundamentação
        contexto = await self.summary_svc.obter_resumo_caso(db, inquerito_id)
        if not contexto:
            contexto = f"Inquérito {numero_inquerito} — informações de contexto não disponíveis."

        prompt = PROMPT_CAUTELAR.format(
            tipo_cautelar=titulo_tipo,
            numero_inquerito=numero_inquerito,
            autoridade=autoridade,
            instrucoes=instrucoes,
            contexto=contexto[:5000],
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="premium",
                temperature=0.4,
                max_tokens=3000,
                agente="AgenteCautelar",
            )

            texto = result["content"].strip()

            # Persistir
            registro = ResultadoAgente(
                inquerito_id=inquerito_id,
                tipo_agente="cautelar",
                resultado_json={"tipo_cautelar": tipo_cautelar, "instrucoes": instrucoes},
                texto_gerado=texto,
                modelo_llm=result.get("model"),
            )
            db.add(registro)
            await db.commit()

            logger.info(f"[AGENTE-CAUTELAR] Minuta '{titulo_tipo}' gerada para {numero_inquerito}.")
            return {
                "tipo": titulo_tipo,
                "inquerito": numero_inquerito,
                "texto_gerado": texto,
                "modelo": result.get("model"),
                "tokens": result.get("usage", {}).get("total_tokens"),
            }

        except Exception as e:
            logger.error(f"[AGENTE-CAUTELAR] Erro: {e}")
            raise
