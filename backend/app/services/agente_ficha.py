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
from app.core.prompts import PROMPT_FICHA_PESSOA, PROMPT_FICHA_EMPRESA, PROMPT_ANALISE_PRELIMINAR, PROMPT_OSINT_WEB
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
                agente="AgenteFicha",
            )

            content = result["content"].strip()
            ficha_json = json.loads(content)

            # Persistir resultado técnico
            registro = ResultadoAgente(
                inquerito_id=inquerito_id,
                tipo_agente="ficha_pessoa",
                referencia_id=pessoa_id,
                resultado_json=ficha_json,
                modelo_llm=result.get("model"),
            )
            db.add(registro)

            # Persistir como Documento Gerado visível para os Autos
            from app.models.documento_gerado import DocumentoGerado
            markdown_content = f"# Ficha de Inteligência: {ficha_json.get('nome', pessoa.nome)}\n\n"
            markdown_content += f"**Risco / Nível:** {ficha_json.get('nivel_risco', ficha_json.get('risco', 'Desconhecido'))}\n\n"
            markdown_content += f"## Resumo Executivo\n{ficha_json.get('perfil_resumido', ficha_json.get('resumo', ''))}\n\n"
            
            if ficha_json.get('pontos_de_atencao'):
                markdown_content += "## Pontos de Atenção\n"
                for ponto in ficha_json['pontos_de_atencao']:
                    markdown_content += f"- {ponto}\n"
                markdown_content += "\n"

            if ficha_json.get('sugestoes_diligencias'):
                markdown_content += "## Sugestões de Diligências\n"
                for sug in ficha_json['sugestoes_diligencias']:
                    markdown_content += f"- {sug}\n"
                markdown_content += "\n"

            doc_gerado = DocumentoGerado(
                inquerito_id=inquerito_id,
                titulo=f"Ficha OSINT: {pessoa.nome}",
                tipo="relatorio",
                conteudo=markdown_content
            )
            db.add(doc_gerado)
            
            await db.commit()

            logger.info(f"[AGENTE-FICHA] Ficha de pessoa {pessoa.nome} gerada e salva nos autos.")
            return ficha_json

        except json.JSONDecodeError as e:
            logger.error(f"[AGENTE-FICHA] Falha ao parsear JSON da ficha: {e}")
            raise
        except Exception as e:
            logger.error(f"[AGENTE-FICHA] Erro ao gerar ficha de pessoa: {e}")
            raise

    async def gerar_analise_preliminar_pessoa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        pessoa_id: uuid.UUID,
        aprimorar: bool = False,
    ) -> Dict[str, Any]:
        """
        Análise investigativa PRELIMINAR usando apenas dados internos dos autos.
        aprimorar=False → tier='resumo' (Groq — gratuito, automático)
        aprimorar=True  → tier='standard' (Gemini Flash — por demanda)
        Não persiste em DocumentoGerado. Cache de 24h em ResultadoAgente.
        """
        from app.models.resultado_agente import ResultadoAgente
        from datetime import timedelta
        from sqlalchemy import and_

        tipo_cache = "preliminar_pessoa_aprimorada" if aprimorar else "preliminar_pessoa"

        # ── Cache: retorna se análise recente já existe (< 24h) ─────────────────
        cache_stmt = (
            select(ResultadoAgente)
            .where(
                and_(
                    ResultadoAgente.inquerito_id == inquerito_id,
                    ResultadoAgente.tipo_agente == tipo_cache,
                    ResultadoAgente.referencia_id == pessoa_id,
                )
            )
            .order_by(ResultadoAgente.created_at.desc())
            .limit(1)
        )
        cache_res = await db.execute(cache_stmt)
        cached = cache_res.scalar_one_or_none()
        if cached:
            age = datetime.utcnow() - cached.created_at.replace(tzinfo=None)
            if age < timedelta(hours=24):
                logger.info(f"[AGENTE-FICHA] Cache hit '{tipo_cache}' para {pessoa_id}")
                return cached.resultado_json

        # ── Buscar dados da pessoa ───────────────────────────────────────────────
        pessoa = await db.get(Pessoa, pessoa_id)
        if not pessoa:
            raise ValueError(f"Pessoa {pessoa_id} não encontrada")

        result_contatos = await db.execute(
            select(Contato)
            .where(Contato.inquerito_id == inquerito_id)
            .where(Contato.pessoa_id == pessoa_id)
        )
        contatos = result_contatos.scalars().all()

        result_end = await db.execute(
            select(Endereco)
            .where(Endereco.inquerito_id == inquerito_id)
            .where(Endereco.pessoa_id == pessoa_id)
        )
        enderecos = result_end.scalars().all()

        result_eventos = await db.execute(
            select(EventoCronologico).where(EventoCronologico.inquerito_id == inquerito_id)
        )
        eventos = result_eventos.scalars().all()

        dados = f"""
Nome: {pessoa.nome}
CPF: {pessoa.cpf or 'Não informado'}
Tipo: {pessoa.tipo_pessoa or 'Não classificado'}
Observações: {pessoa.observacoes or 'Nenhuma'}

Contatos:
{chr(10).join(f"- {c.tipo_contato}: {c.valor}" for c in contatos) or "Nenhum"}

Endereços:
{chr(10).join(f"- {e.endereco_completo} ({e.cidade}/{e.estado})" for e in enderecos) or "Nenhum"}

Eventos/Cronologia:
{chr(10).join(f"- {ev.data_fato_str or str(ev.data_fato or '')}: {ev.descricao}" for ev in eventos[:15]) or "Nenhum"}
        """.strip()

        historico_str = "Nenhum registro em outros inquéritos."
        if pessoa.cpf:
            try:
                historico = await buscar_historico_pessoa(db, pessoa.cpf, inquerito_id)
                if historico:
                    historico_str = "\n".join(
                        f"- IP {h['numero']} ({h['ano'] or '?'}): {h['tipo_pessoa']} — {h['descricao'] or 'sem descrição'}"
                        for h in historico
                    )
            except Exception as e:
                logger.warning(f"[AGENTE-FICHA] Histórico cruzado falhou: {e}")

        prompt = PROMPT_ANALISE_PRELIMINAR.format(
            nome=pessoa.nome,
            dados_consolidados=dados,
            historico_inqueritos=historico_str,
        )

        tier = "standard" if aprimorar else "resumo"
        result = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier=tier,
            temperature=0.2,
            max_tokens=1200,
            json_mode=True,
            agente="AnalisePreliminar",
        )

        raw_prelim = result["content"].strip()
        if raw_prelim.startswith("```"):
            raw_prelim = raw_prelim.split("```", 2)[1]
            if raw_prelim.startswith("json"):
                raw_prelim = raw_prelim[4:]
            raw_prelim = raw_prelim.strip()
        try:
            analise_json = json.loads(raw_prelim)
        except json.JSONDecodeError as e:
            logger.error(f"[AGENTE-FICHA] JSON inválido na análise preliminar: {e}")
            raise RuntimeError(f"LLM retornou JSON inválido: {e}") from e
        analise_json["_fonte"] = "gemini-flash" if aprimorar else "groq"

        # Persistir cache
        registro = ResultadoAgente(
            inquerito_id=inquerito_id,
            tipo_agente=tipo_cache,
            referencia_id=pessoa_id,
            resultado_json=analise_json,
            modelo_llm=result.get("model"),
        )
        db.add(registro)
        await db.commit()

        logger.info(f"[AGENTE-FICHA] Análise preliminar ({tier}) gerada para {pessoa.nome}")
        return analise_json

    async def gerar_osint_web_pessoa(
        self,
        db: AsyncSession,
        inquerito_id: uuid.UUID,
        pessoa_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Busca fontes abertas (web) para a pessoa via Serper.dev + consolida com Gemini Flash.
        Cache de 6h em ResultadoAgente (tipo_agente='osint_web_pessoa').
        """
        from datetime import timedelta
        from sqlalchemy import and_

        # ── Cache 6h ──────────────────────────────────────────────────────────
        cache_stmt = (
            select(ResultadoAgente)
            .where(and_(
                ResultadoAgente.inquerito_id == inquerito_id,
                ResultadoAgente.tipo_agente == "osint_web_pessoa",
                ResultadoAgente.referencia_id == pessoa_id,
            ))
            .order_by(ResultadoAgente.created_at.desc())
            .limit(1)
        )
        cached = (await db.execute(cache_stmt)).scalar_one_or_none()
        if cached:
            from datetime import datetime as dt
            age = dt.utcnow() - cached.created_at.replace(tzinfo=None)
            if age < timedelta(hours=6):
                logger.info(f"[AGENTE-FICHA] Cache hit 'osint_web_pessoa' para {pessoa_id}")
                return cached.resultado_json

        pessoa = await db.get(Pessoa, pessoa_id)
        if not pessoa:
            raise ValueError(f"Pessoa {pessoa_id} não encontrada")

        # ── Serper: buscas web paralelas ───────────────────────────────────────
        from app.services.serper_service import SerperService
        cpf_limpo = pessoa.cpf.replace(".", "").replace("-", "").strip() if pessoa.cpf else None
        serper = SerperService()
        dados_web = await serper.buscar_pessoa(nome=pessoa.nome, cpf=cpf_limpo)

        # Formatar snippets para o prompt
        blocos = []
        for cat, resultados in dados_web["por_categoria"].items():
            blocos.append(f"[{cat.upper()}]")
            for r in resultados[:2]:  # max 2 por categoria
                trecho = (r['trecho'] or '')[:120]
                blocos.append(f"- {r['titulo'][:80]}\n  {trecho}")
        resultados_str = "\n".join(blocos) or "Sem resultados encontrados."

        dados_internos = (
            f"Nome: {pessoa.nome}\n"
            f"CPF: {pessoa.cpf or 'não consta'}\n"
            f"Papel: {getattr(pessoa, 'papel', None) or 'não identificado'}"
        )

        # ── LLM ───────────────────────────────────────────────────────────────
        prompt = PROMPT_OSINT_WEB.format(
            nome=pessoa.nome,
            resultados_web=resultados_str,
            dados_internos=dados_internos,
        )
        result = await self.llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="standard",
            temperature=0.1,
            max_tokens=2500,
            json_mode=True,
            agente="OsintWeb",
        )
        raw = result["content"].strip()
        # Remove markdown code fences que alguns modelos inserem
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            analise = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[AGENTE-FICHA] JSON inválido no OSINT web: {e} | raw={raw[:200]}")
            raise RuntimeError(f"LLM retornou JSON inválido: {e}") from e
        analise["_fonte"] = "serper"
        analise["termos_buscados"] = dados_web["termos_buscados"]
        analise["total_resultados"] = dados_web["total_resultados"]

        # ── Cache ──────────────────────────────────────────────────────────────
        registro = ResultadoAgente(
            inquerito_id=inquerito_id,
            tipo_agente="osint_web_pessoa",
            referencia_id=pessoa_id,
            resultado_json=analise,
            modelo_llm=result.get("model"),
        )
        db.add(registro)
        await db.commit()

        logger.info(f"[AGENTE-FICHA] OSINT web gerado para {pessoa.nome} ({dados_web['total_resultados']} resultados)")
        return analise

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
                agente="AgenteFicha",
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

            # Persistir como Documento Gerado visível para os Autos
            from app.models.documento_gerado import DocumentoGerado
            markdown_content = f"# Ficha de Inteligência: {ficha_json.get('nome', empresa.nome)}\n\n"
            markdown_content += f"**Risco / Nível:** {ficha_json.get('nivel_risco', ficha_json.get('risco', 'Desconhecido'))}\n\n"
            markdown_content += f"## Resumo Executivo\n{ficha_json.get('perfil_resumido', ficha_json.get('resumo', ''))}\n\n"
            
            if ficha_json.get('pontos_de_atencao'):
                markdown_content += "## Pontos de Atenção\n"
                for ponto in ficha_json['pontos_de_atencao']:
                    markdown_content += f"- {ponto}\n"
                markdown_content += "\n"

            if ficha_json.get('sugestoes_diligencias'):
                markdown_content += "## Sugestões de Diligências\n"
                for sug in ficha_json['sugestoes_diligencias']:
                    markdown_content += f"- {sug}\n"
                markdown_content += "\n"

            doc_gerado = DocumentoGerado(
                inquerito_id=inquerito_id,
                titulo=f"Ficha OSINT: {empresa.nome}",
                tipo="relatorio",
                conteudo=markdown_content
            )
            db.add(doc_gerado)

            await db.commit()

            logger.info(f"[AGENTE-FICHA] Ficha de empresa {empresa.nome} gerada e salva nos autos.")
            return ficha_json

        except Exception as e:
            logger.error(f"[AGENTE-FICHA] Erro ao gerar ficha de empresa: {e}")
            raise
