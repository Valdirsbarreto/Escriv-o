"""
Escrivão AI — Task Celery: OSINT Aprofundado (Gemini Deep Research Agent)
Pesquisa autônoma multi-etapas em fontes abertas. Pode levar 5–15 min.

Fluxo:
1. Busca dados internos da Pessoa (nome, CPF, papel, contatos, endereços, eventos)
2. Monta prompt investigativo em português
3. client.interactions.create(background=True) → obtém interaction_id
4. Loop de polling a cada 15s até status == "completed" ou "failed"
5. Substitui placeholder __PROCESSANDO__ com resultado Markdown
6. Registra ConsultaExterna com custo estimado
7. Notifica Telegram
"""

import asyncio
import logging
import time
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DEEP_RESEARCH_AGENT = "deep-research-preview-04-2026"
POLLING_INTERVAL_S = 15
MAX_POLL_ITERATIONS = 80   # 80 × 15s = 20 min máximo
CUSTO_ESTIMADO_USD = 2.00  # estimativa conservadora por pesquisa


@celery_app.task(
    bind=True,
    name="app.workers.osint_deep_task.osint_deep_research_task",
    max_retries=0,
    time_limit=1320,
    soft_time_limit=1260,
)
def osint_deep_research_task(self, inquerito_id: str, pessoa_id: str, doc_id: str, briefing_override: str | None = None):
    """
    Executa pesquisa aprofundada via Gemini Deep Research Agent.
    Parâmetros:
        inquerito_id: UUID do inquérito
        pessoa_id: UUID da pessoa alvo
        doc_id: UUID do DocumentoGerado placeholder já criado (conteudo="__PROCESSANDO__")
        briefing_override: briefing aprovado/editado pelo Comissário (pula _gerar_briefing se fornecido)
    """
    logger.info(f"[OSINT-DEEP] Iniciando — inquerito={inquerito_id} pessoa={pessoa_id} doc={doc_id} briefing_override={'sim' if briefing_override else 'não'}")

    async def _run():
        from app.core.config import settings
        from app.core.database import _encode_password_in_url
        from app.models.pessoa import Pessoa
        from app.models.contato import Contato
        from app.models.endereco import Endereco
        from app.models.documento_gerado import DocumentoGerado
        from app.models.consulta_externa import ConsultaExterna
        from sqlalchemy.pool import NullPool
        import ssl

        # ── Engine async para o worker ────────────────────────────────────────
        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)
        connect_args: dict = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        engine = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        inq_uuid = uuid.UUID(inquerito_id)
        pessoa_uuid = uuid.UUID(pessoa_id)
        doc_uuid = uuid.UUID(doc_id)

        async with AsyncSession_(expire_on_commit=False) as db:

            # ── 1. Buscar dados da pessoa ─────────────────────────────────────
            pessoa = await db.get(Pessoa, pessoa_uuid)
            if not pessoa:
                logger.error(f"[OSINT-DEEP] Pessoa não encontrada: {pessoa_id}")
                await _marcar_erro(db, doc_uuid, "Pessoa não encontrada no banco de dados.")
                await engine.dispose()
                return None

            contatos_res = await db.execute(
                select(Contato)
                .where(Contato.inquerito_id == inq_uuid, Contato.pessoa_id == pessoa_uuid)
                .limit(10)
            )
            contatos = contatos_res.scalars().all()

            enderecos_res = await db.execute(
                select(Endereco)
                .where(Endereco.inquerito_id == inq_uuid, Endereco.pessoa_id == pessoa_uuid)
                .limit(5)
            )
            enderecos = enderecos_res.scalars().all()

            # ── 2. Buscar contexto do inquérito para briefing ─────────────────
            from app.models.documento_gerado import DocumentoGerado as DocGerado
            from app.services.summary_service import SummaryService

            contexto_parts = []
            try:
                rel_res = await db.execute(
                    select(DocGerado)
                    .where(
                        DocGerado.inquerito_id == inq_uuid,
                        DocGerado.tipo == "relatorio_inicial",
                        DocGerado.conteudo != "__PROCESSANDO__",
                    )
                    .order_by(DocGerado.created_at.desc())
                    .limit(1)
                )
                rel = rel_res.scalar_one_or_none()
                if rel and rel.conteudo:
                    contexto_parts.append("=== RELATÓRIO INICIAL ===\n" + rel.conteudo[:8000])

                resumo = await SummaryService().obter_resumo_caso(db, inq_uuid)
                if resumo:
                    contexto_parts.append("=== RESUMO EXECUTIVO ===\n" + resumo[:3000])
            except Exception as e:
                logger.warning(f"[OSINT-DEEP] Contexto parcial para briefing: {e}")

            contexto_inquerito = "\n\n".join(contexto_parts) or "Contexto do inquérito não disponível."

            # ── 2b. Briefing — usa override aprovado pelo Comissário ou gera novo ──
            if briefing_override:
                briefing = briefing_override
                logger.info(f"[OSINT-DEEP] Usando briefing aprovado pelo Comissário ({len(briefing)} chars) para {pessoa.nome}")
            else:
                briefing = await _gerar_briefing(pessoa, contatos, enderecos, contexto_inquerito)
                logger.info(f"[OSINT-DEEP] Briefing gerado automaticamente ({len(briefing)} chars) para {pessoa.nome}")

            # ── 3. Montar prompt final e iniciar Deep Research ────────────────
            prompt = _montar_prompt_com_briefing(pessoa, contatos, enderecos, briefing)

            # ── Iniciar Deep Research ─────────────────────────────────────────
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            try:
                interaction = client.interactions.create(
                    input=prompt,
                    agent=DEEP_RESEARCH_AGENT,
                    background=True,
                )
                interaction_id = interaction.id
                logger.info(f"[OSINT-DEEP] Interaction {interaction_id} criada para {pessoa.nome}")
            except Exception as e:
                logger.error(f"[OSINT-DEEP] Falha ao criar interaction: {e}")
                await _marcar_erro(db, doc_uuid, f"Falha ao iniciar Deep Research: {str(e)[:300]}")
                await engine.dispose()
                return None

            # ── 4. Polling ────────────────────────────────────────────────────
            resultado_texto = None
            for i in range(MAX_POLL_ITERATIONS):
                time.sleep(POLLING_INTERVAL_S)
                try:
                    interaction = client.interactions.get(interaction_id)
                    logger.info(
                        f"[OSINT-DEEP] Poll {i+1}/{MAX_POLL_ITERATIONS} "
                        f"status={interaction.status} ({interaction_id})"
                    )
                    if interaction.status == "completed":
                        if interaction.outputs:
                            # Log estrutura de outputs para diagnóstico
                            for j, out in enumerate(interaction.outputs):
                                txt_len = len(out.text or "")
                                logger.info(f"[OSINT-DEEP] Output[{j}]: {txt_len} chars")
                            # Pega o output mais substancial (maior texto), não necessariamente o último
                            candidatos = [(len(o.text or ""), o.text) for o in interaction.outputs if o.text]
                            if candidatos:
                                resultado_texto = max(candidatos, key=lambda x: x[0])[1]
                        break
                    elif interaction.status in ("failed", "cancelled"):
                        logger.warning(f"[OSINT-DEEP] Interaction {interaction.status}")
                        break
                except Exception as e:
                    logger.warning(f"[OSINT-DEEP] Erro no poll {i+1}: {e}")
                    continue

            # ── 4b. Pós-processamento: conclusão investigativa ────────────────
            conclusao = ""
            if resultado_texto:
                papel = getattr(pessoa, "papel", None) or getattr(pessoa, "tipo_pessoa", "não identificado")
                conclusao = await _gerar_conclusao(
                    pessoa.nome, papel, resultado_texto, contexto_inquerito
                )
                if conclusao:
                    logger.info(f"[OSINT-DEEP] Conclusão gerada ({len(conclusao)} chars)")

            # ── 5. Persistir resultado ────────────────────────────────────────
            doc = await db.get(DocumentoGerado, doc_uuid)
            if not doc:
                logger.error(f"[OSINT-DEEP] DocumentoGerado não encontrado: {doc_id}")
                await engine.dispose()
                return None

            if resultado_texto:
                doc.conteudo = _formatar_resultado(pessoa.nome, resultado_texto, conclusao)
                doc.modelo_llm = DEEP_RESEARCH_AGENT
                logger.info(f"[OSINT-DEEP] Resultado salvo: {len(resultado_texto)} chars para {pessoa.nome}")
            else:
                doc.conteudo = (
                    f"# OSINT Aprofundado — {pessoa.nome}\n\n"
                    f"**AVISO:** A pesquisa Deep Research não retornou resultado.\n"
                    f"O agente pode ter atingido timeout ou erro interno.\n\n"
                    f"_Interaction ID: {interaction_id}_\n\n"
                    f"Tente novamente em alguns minutos."
                )
                logger.warning(f"[OSINT-DEEP] Sem resultado para {pessoa.nome}")

            # ── 6. Registrar ConsultaExterna (rastreamento de custo) ──────────
            if resultado_texto:
                doc_hash = ConsultaExterna.hash_documento(str(pessoa_uuid))
                consulta = ConsultaExterna(
                    inquerito_id=inq_uuid,
                    tipo_consulta="osint_deep_research",
                    documento_hash=doc_hash,
                    custo_estimado=Decimal(str(CUSTO_ESTIMADO_USD * _cotacao_brl())),
                    status="ok",
                    resultado_json={"interaction_id": interaction_id, "chars": len(resultado_texto)},
                )
                db.add(consulta)

            await db.commit()

        await engine.dispose()

        # ── 7. Notificar Telegram ─────────────────────────────────────────────
        if resultado_texto:
            await _notificar_telegram(pessoa.nome, inquerito_id)

        return {"status": "concluido" if resultado_texto else "sem_resultado", "pessoa": pessoa.nome}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[OSINT-DEEP] Finalizado: {result}")
        return result
    except Exception as e:
        logger.error(f"[OSINT-DEEP] Erro fatal: {e}", exc_info=True)
        motivo = "Tempo limite da tarefa excedido (SoftTimeLimitExceeded)." if "SoftTimeLimitExceeded" in type(e).__name__ else str(e)[:200]
        asyncio.run(_limpar_placeholder_sync(doc_id, motivo=motivo))
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _gerar_briefing(pessoa, contatos, enderecos, contexto_inquerito: str) -> str:
    """
    Chama gemini-flash (tier standard) para gerar um briefing investigativo
    sob medida, considerando o contexto real dos autos e o papel da pessoa.
    Fallback para prompt genérico em caso de erro.
    """
    from app.core.prompts import PROMPT_OSINT_DEEP_BRIEFING
    from app.services.llm_service import LLMService

    linhas_contato = "; ".join(f"{c.tipo_contato}: {c.valor}" for c in contatos) or "não informado"
    linhas_end = "; ".join(
        f"{e.endereco_completo} ({getattr(e,'cidade','')})" for e in enderecos
    ) or "não informado"
    cpf_doc = pessoa.cpf or getattr(pessoa, "cnpj", None) or "não informado"
    papel = getattr(pessoa, "papel", None) or getattr(pessoa, "tipo_pessoa", "não identificado")

    prompt = PROMPT_OSINT_DEEP_BRIEFING.format(
        contexto_inquerito=contexto_inquerito,
        nome=pessoa.nome,
        documento=cpf_doc,
        papel=papel,
        contatos=linhas_contato,
        enderecos=linhas_end,
    )

    try:
        llm = LLMService()
        result = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="standard",
            temperature=0.1,
            max_tokens=65536,
            agente="OsintDeepBriefing",
        )
        return result["content"].strip()
    except Exception as e:
        logger.warning(f"[OSINT-DEEP] Falha no briefing LLM, usando template genérico: {e}")
        return ""


async def _gerar_conclusao(nome: str, papel: str, resultado_osint: str, contexto_inquerito: str) -> str:
    """
    Pós-processa o resultado bruto do Deep Research:
    cruza achados OSINT com os autos e extrai diligências concretas.
    Usa gemini-flash (tier standard) — rápido e econômico para este passo.
    """
    from app.core.prompts import PROMPT_OSINT_DEEP_CONCLUSAO
    from app.services.llm_service import LLMService

    prompt = PROMPT_OSINT_DEEP_CONCLUSAO.format(
        contexto_inquerito=contexto_inquerito[:5000],
        nome=nome,
        papel=papel,
        resultado_osint=resultado_osint[:15000],
    )

    try:
        llm = LLMService()
        result = await llm.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            tier="standard",
            temperature=0.1,
            max_tokens=65536,
            agente="OsintDeepConclusao",
        )
        return result["content"].strip()
    except Exception as e:
        logger.warning(f"[OSINT-DEEP] Falha na conclusão investigativa: {e}")
        return ""


def _montar_prompt(pessoa, contatos, enderecos) -> str:
    linhas_contato = "\n".join(
        f"- {c.tipo_contato}: {c.valor}" for c in contatos
    ) or "Não informado"
    linhas_end = "\n".join(
        f"- {e.endereco_completo} ({getattr(e, 'cidade', '')} / {getattr(e, 'estado', '')})"
        for e in enderecos
    ) or "Não informado"
    cpf_info = f"CPF: {pessoa.cpf}" if pessoa.cpf else "CPF não informado"
    cnpj_info = f" | CNPJ: {pessoa.cnpj}" if getattr(pessoa, "cnpj", None) else ""
    papel = getattr(pessoa, "papel", None) or getattr(pessoa, "tipo_pessoa", "não identificado")

    return f"""Realize uma pesquisa investigativa aprofundada em fontes abertas sobre a pessoa a seguir, alvo de investigação policial no Brasil (PCERJ):

**Nome completo:** {pessoa.nome}
**{cpf_info}{cnpj_info}**
**Papel na investigação:** {papel}

**Contatos registrados nos autos:**
{linhas_contato}

**Endereços conhecidos:**
{linhas_end}

**Objetivos da pesquisa — responda cada tópico:**
1. Presença digital: perfis em redes sociais (LinkedIn, Facebook, Instagram, X/Twitter), sites pessoais
2. Vínculos empresariais: sócios, CNPJs associados, empresas abertas/encerradas (Receita Federal, Junta Comercial)
3. Processos judiciais: TJ-RJ, TRF, STJ, STF, JusBrasil, Escavador (cível, criminal, trabalhista)
4. Menções em mídia: notícias policiais, investigações jornalísticas, reportagens
5. Registros oficiais: Diário Oficial (nomeações, contratos, sanções), CGU/CEIS/CNEP, OFAC/ONU
6. Patrimônio identificável: imóveis (cartórios), veículos (DETRAN-RJ), aeronaves, embarcações
7. Relacionamentos relevantes: familiares, sócios, associados com histórico criminal
8. Indicadores de incompatibilidade patrimonial com a função declarada

**Formato esperado:**
Relatório investigativo em Markdown, seções numeradas conforme os tópicos acima, fontes citadas com URLs quando disponíveis. Destaque achados críticos. Seja factual — cite apenas o que encontrar nas fontes, sem especulação. Redija em português do Brasil."""


def _montar_prompt_com_briefing(pessoa, contatos, enderecos, briefing: str) -> str:
    """
    Combina o briefing investigativo gerado pelo LLM com os dados factuais
    da pessoa para criar o prompt final do Deep Research Agent.
    Se o briefing falhou (string vazia), usa o template genérico como fallback.
    """
    if not briefing:
        return _montar_prompt(pessoa, contatos, enderecos)

    cpf_info = f"CPF: {pessoa.cpf}" if pessoa.cpf else "CPF não informado"
    cnpj_info = f" | CNPJ: {pessoa.cnpj}" if getattr(pessoa, "cnpj", None) else ""
    papel = getattr(pessoa, "papel", None) or getattr(pessoa, "tipo_pessoa", "não identificado")
    linhas_contato = "\n".join(f"- {c.tipo_contato}: {c.valor}" for c in contatos) or "Não informado"
    linhas_end = "\n".join(
        f"- {e.endereco_completo} ({getattr(e, 'cidade', '')} / {getattr(e, 'estado', '')})"
        for e in enderecos
    ) or "Não informado"

    return f"""Você é um agente de pesquisa OSINT especializado em investigações criminais no Brasil.

=== ALVO ===
Nome: {pessoa.nome}
{cpf_info}{cnpj_info}
Papel: {papel}

Contatos: {linhas_contato}
Endereços: {linhas_end}

=== BRIEFING INVESTIGATIVO (elaborado pelo analista de inteligência criminal) ===
{briefing}

=== INSTRUÇÕES ===
Realize a pesquisa seguindo rigorosamente o briefing acima.
- Priorize as fontes indicadas pelo analista para este caso específico
- Cite URLs e datas de publicação sempre que disponíveis
- Separe claramente o que é fato encontrado do que é inferência
- Relatório final em Markdown, em português do Brasil
- Destaque em negrito qualquer achado crítico para a investigação"""


def _separar_fontes(texto: str) -> tuple[str, list[str]]:
    """Separa linhas que são apenas URLs/domínios do conteúdo analítico.
    Retorna (conteudo_limpo, lista_de_fontes).
    """
    import re
    url_pattern = re.compile(
        r"^\s*(https?://\S+|[\w.-]+\.(com|com\.br|org|gov|jus|mp|edu|net|io|br|uy|ar|pt)(\.br)?(/\S*)?)\s*$",
        re.IGNORECASE,
    )
    conteudo_lines: list[str] = []
    fontes: list[str] = []
    for line in texto.splitlines():
        if url_pattern.match(line):
            url = line.strip()
            if url and url not in fontes:
                fontes.append(url)
        else:
            conteudo_lines.append(line)
    # Remove blocos de linhas em branco consecutivos deixados pela extração
    conteudo = re.sub(r"\n{3,}", "\n\n", "\n".join(conteudo_lines)).strip()
    return conteudo, fontes


def _formatar_resultado(nome: str, texto: str, conclusao: str = "") -> str:
    data_fmt = date.today().strftime("%d/%m/%Y")

    conteudo, fontes = _separar_fontes(texto)

    fontes_bloco = ""
    if fontes:
        lista = "\n".join(f"- {f}" for f in fontes[:50])  # limita a 50 fontes
        fontes_bloco = f"\n\n<details>\n<summary>🔗 Fontes consultadas ({len(fontes)})</summary>\n\n{lista}\n\n</details>"

    conclusao_bloco = (
        f"\n\n---\n\n## Conclusão Investigativa e Diligências Sugeridas\n\n{conclusao}"
        if conclusao
        else ""
    )
    return (
        f"# OSINT Aprofundado — {nome}\n\n"
        f"**Gerado em:** {data_fmt}  \n"
        f"**Motor:** Gemini Deep Research Agent  \n"
        f"> ⚠️ Dados obtidos de fontes abertas na internet. Verificar antes de usar como elemento probatório.\n\n"
        f"---\n\n"
        f"{conteudo}"
        f"{fontes_bloco}"
        f"{conclusao_bloco}"
    )


def _cotacao_brl() -> float:
    try:
        from app.core.config import settings
        return float(getattr(settings, "COTACAO_DOLAR_BRL", 5.80))
    except Exception:
        return 5.80


async def _marcar_erro(db: AsyncSession, doc_uuid: uuid.UUID, mensagem: str):
    from app.models.documento_gerado import DocumentoGerado
    doc = await db.get(DocumentoGerado, doc_uuid)
    if doc:
        doc.conteudo = f"# ERRO — OSINT Aprofundado\n\n{mensagem}"
        await db.commit()


async def _limpar_placeholder_sync(doc_id: str, motivo: str = "Timeout ou erro fatal na task."):
    """Marca o placeholder __PROCESSANDO__ como erro em caso de falha fatal."""
    try:
        from app.core.config import settings
        from app.core.database import _encode_password_in_url
        from app.models.documento_gerado import DocumentoGerado
        from sqlalchemy.pool import NullPool
        import ssl

        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)
        connect_args: dict = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        engine2 = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSession2() as db2:
            doc = await db2.get(DocumentoGerado, uuid.UUID(doc_id))
            if doc and doc.conteudo == "__PROCESSANDO__":
                doc.conteudo = (
                    f"# ERRO — OSINT Aprofundado\n\n"
                    f"A pesquisa foi interrompida antes de concluir.\n\n"
                    f"**Motivo:** {motivo}\n\n"
                    f"Tente novamente — o Deep Research às vezes excede o tempo limite. "
                    f"Use o briefing editável para refinar o escopo e reduzir o tempo de pesquisa."
                )
                await db2.commit()
        await engine2.dispose()
    except Exception as e:
        logger.warning(f"[OSINT-DEEP] Falha ao marcar placeholder como erro: {e}")


async def _notificar_telegram(nome_pessoa: str, inquerito_id: str):
    try:
        from app.core.config import settings
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ALLOWED_USER_IDS:
            return
        user_ids = [
            int(uid.strip())
            for uid in settings.TELEGRAM_ALLOWED_USER_IDS.split(",")
            if uid.strip().isdigit()
        ]
        if not user_ids:
            return
        import httpx
        mensagem = (
            f"🔍 <b>OSINT Aprofundado concluído</b>\n\n"
            f"Alvo: <b>{nome_pessoa}</b>\n"
            f"Inquérito: <code>{inquerito_id[:8]}…</code>\n\n"
            f"Relatório disponível em <b>Documentos IA</b> do workspace."
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            for uid in user_ids:
                await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": uid, "text": mensagem, "parse_mode": "HTML"},
                )
    except Exception as e:
        logger.warning(f"[OSINT-DEEP] Falha na notificação Telegram: {e}")
