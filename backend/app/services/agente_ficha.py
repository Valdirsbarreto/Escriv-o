"""
Escrivão AI — Agente: Fichas Investigativas (OSINT interno)
Consolida dados de Pessoa/Empresa já indexados e gera ficha via LLM Premium.
Conforme blueprint §9.1 (Agente de Fichas).
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService
from app.core.prompts import PROMPT_FICHA_PESSOA, PROMPT_FICHA_EMPRESA
from app.models.pessoa import Pessoa
from app.models.empresa import Empresa
from app.models.endereco import Endereco
from app.models.contato import Contato
from app.models.evento_cronologico import EventoCronologico
from app.models.resultado_agente import ResultadoAgente
from app.services.copiloto_osint_service import buscar_historico_pessoa, buscar_historico_empresa

logger = logging.getLogger(__name__)


class AgenteFicha:
    """Gera fichas investigativas de Pessoas e Empresas com dados internos do banco."""

    def __init__(self):
        self.llm = LLMService()

    async def gerar_ficha_pessoa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        pessoa_id: uuid.UUID,
        dados_externos: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Consolida todos os dados internos de uma pessoa e gera ficha investigativa.
        """
        # ── Buscar todos os dados da pessoa ──────────────────
        pessoa = await db.get(Pessoa, pessoa_id)
        if not pessoa:
            raise ValueError(f"Pessoa {pessoa_id} não encontrada")

        # Contatos
        result_contatos = await db.execute(
            select(Contato)
            .where(Contato.inquerito_id == inquerito_id)
            .where(Contato.pessoa_id == pessoa_id)
        )
        contatos = result_contatos.scalars().all()

        # Endereços
        result_end = await db.execute(
            select(Endereco)
            .where(Endereco.inquerito_id == inquerito_id)
            .where(Endereco.pessoa_id == pessoa_id)
        )
        enderecos = result_end.scalars().all()

        # Eventos cronológicos onde aparece
        result_eventos = await db.execute(
            select(EventoCronologico)
            .where(EventoCronologico.inquerito_id == inquerito_id)
        )
        eventos = result_eventos.scalars().all()

        # Montar dados consolidados
        dados = f"""
Nome: {pessoa.nome}
CPF: {pessoa.cpf or 'Não informado'}
Tipo: {pessoa.tipo_pessoa or 'Não classificado'}
Observações: {pessoa.observacoes or 'Nenhuma'}

Contatos registrados:
{chr(10).join(f"- {c.tipo_contato}: {c.valor}" for c in contatos) or "Nenhum"}

Endereços:
{chr(10).join(f"- {e.endereco_completo} ({e.cidade}/{e.estado})" for e in enderecos) or "Nenhum"}

Eventos/Cronologia:
{chr(10).join(f"- {ev.data_fato_str or str(ev.data_fato or '')}: {ev.descricao}" for ev in eventos[:20]) or "Nenhum"}
        """.strip()

        dados_externos_str = (
            json.dumps(dados_externos, ensure_ascii=False, indent=2)
            if dados_externos
            else "Não solicitado."
        )

        # Histórico cruzado
        historico_str = "Nenhum registro encontrado em outros inquéritos."
        if pessoa.cpf:
            try:
                historico = await buscar_historico_pessoa(db, pessoa.cpf, inquerito_id)
                if historico:
                    linhas = [
                        f"- Inquérito {h['numero']} ({h['ano'] or 'ano desconhecido'}): "
                        f"{h['tipo_pessoa']} — {h['descricao'] or 'sem descrição'}"
                        for h in historico
                    ]
                    historico_str = "\n".join(linhas)
            except Exception as e:
                logger.warning(f"[AGENTE-FICHA] Histórico cruzado falhou: {e}")

        prompt = PROMPT_FICHA_PESSOA.format(
            nome=pessoa.nome,
            dados_consolidados=dados,
            historico_inqueritos=historico_str,
            dados_externos=dados_externos_str,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="premium",
                temperature=0.2,
                max_tokens=2000,
                json_mode=True,
            )

            content = result["content"].strip()
            ficha_json = json.loads(content)

            # Persistir resultado
            registro = ResultadoAgente(
                inquerito_id=inquerito_id,
                tipo_agente="ficha_pessoa",
                referencia_id=pessoa_id,
                resultado_json=ficha_json,
                modelo_llm=result.get("model"),
            )
            db.add(registro)
            await db.commit()

            logger.info(f"[AGENTE-FICHA] Ficha de pessoa {pessoa.nome} gerada.")
            return ficha_json

        except json.JSONDecodeError as e:
            logger.error(f"[AGENTE-FICHA] Falha ao parsear JSON da ficha: {e}")
            raise
        except Exception as e:
            logger.error(f"[AGENTE-FICHA] Erro ao gerar ficha de pessoa: {e}")
            raise

    async def gerar_ficha_empresa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        empresa_id: uuid.UUID,
        dados_externos: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Consolida todos os dados internos de uma empresa e gera ficha investigativa.
        """
        empresa = await db.get(Empresa, empresa_id)
        if not empresa:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        # Endereços
        result_end = await db.execute(
            select(Endereco)
            .where(Endereco.inquerito_id == inquerito_id)
            .where(Endereco.empresa_id == empresa_id)
        )
        enderecos = result_end.scalars().all()

        dados = f"""
Nome/Razão Social: {empresa.nome}
CNPJ: {empresa.cnpj or 'Não informado'}
Tipo: {empresa.tipo_empresa or 'Não classificado'}
Observações: {empresa.observacoes or 'Nenhuma'}

Endereços:
{chr(10).join(f"- {e.endereco_completo} ({e.cidade}/{e.estado})" for e in enderecos) or "Nenhum"}
        """.strip()

        dados_externos_str = (
            json.dumps(dados_externos, ensure_ascii=False, indent=2)
            if dados_externos
            else "Não solicitado."
        )

        # Histórico cruzado
        historico_str = "Nenhum registro encontrado em outros inquéritos."
        if empresa.cnpj:
            try:
                historico = await buscar_historico_empresa(db, empresa.cnpj, inquerito_id)
                if historico:
                    linhas = [
                        f"- Inquérito {h['numero']} ({h['ano'] or 'ano desconhecido'}): "
                        f"{h['tipo_empresa']} — {h['descricao'] or 'sem descrição'}"
                        for h in historico
                    ]
                    historico_str = "\n".join(linhas)
            except Exception as e:
                logger.warning(f"[AGENTE-FICHA] Histórico cruzado empresa falhou: {e}")

        prompt = PROMPT_FICHA_EMPRESA.format(
            nome=empresa.nome,
            dados_consolidados=dados,
            historico_inqueritos=historico_str,
            dados_externos=dados_externos_str,
        )

        try:
            result = await self.llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="premium",
                temperature=0.2,
                max_tokens=1500,
                json_mode=True,
            )

            ficha_json = json.loads(result["content"].strip())

            registro = ResultadoAgente(
                inquerito_id=inquerito_id,
                tipo_agente="ficha_empresa",
                referencia_id=empresa_id,
                resultado_json=ficha_json,
                modelo_llm=result.get("model"),
            )
            db.add(registro)
            await db.commit()

            logger.info(f"[AGENTE-FICHA] Ficha de empresa {empresa.nome} gerada.")
            return ficha_json

        except Exception as e:
            logger.error(f"[AGENTE-FICHA] Erro ao gerar ficha de empresa: {e}")
            raise
