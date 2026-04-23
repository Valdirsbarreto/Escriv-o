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
def osint_deep_research_task(self, inquerito_id: str, pessoa_id: str, doc_id: str):
    """
    Executa pesquisa aprofundada via Gemini Deep Research Agent.
    Parâmetros:
        inquerito_id: UUID do inquérito
        pessoa_id: UUID da pessoa alvo
        doc_id: UUID do DocumentoGerado placeholder já criado (conteudo="__PROCESSANDO__")
    """
    logger.info(f"[OSINT-DEEP] Iniciando — inquerito={inquerito_id} pessoa={pessoa_id} doc={doc_id}")

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

            # ── 2. Montar prompt investigativo ────────────────────────────────
            prompt = _montar_prompt(pessoa, contatos, enderecos)

            # ── 3. Iniciar Deep Research ──────────────────────────────────────
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
                            resultado_texto = interaction.outputs[-1].text
                        break
                    elif interaction.status in ("failed", "cancelled"):
                        logger.warning(f"[OSINT-DEEP] Interaction {interaction.status}")
                        break
                except Exception as e:
                    logger.warning(f"[OSINT-DEEP] Erro no poll {i+1}: {e}")
                    continue

            # ── 5. Persistir resultado ────────────────────────────────────────
            doc = await db.get(DocumentoGerado, doc_uuid)
            if not doc:
                logger.error(f"[OSINT-DEEP] DocumentoGerado não encontrado: {doc_id}")
                await engine.dispose()
                return None

            if resultado_texto:
                doc.conteudo = _formatar_resultado(pessoa.nome, resultado_texto)
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
        asyncio.run(_limpar_placeholder_sync(doc_id))
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _formatar_resultado(nome: str, texto: str) -> str:
    data_fmt = date.today().strftime("%d/%m/%Y")
    return (
        f"# OSINT Aprofundado — {nome}\n\n"
        f"**Gerado em:** {data_fmt}  \n"
        f"**Motor:** Gemini Deep Research Agent  \n"
        f"> ⚠️ Dados obtidos de fontes abertas na internet. Verificar antes de usar como elemento probatório.\n\n"
        f"---\n\n"
        f"{texto}"
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


async def _limpar_placeholder_sync(doc_id: str):
    """Remove o placeholder __PROCESSANDO__ em caso de erro fatal não tratado."""
    try:
        from app.core.config import settings
        from app.core.database import _encode_password_in_url
        from app.models.documento_gerado import DocumentoGerado
        from sqlalchemy import delete as sa_delete
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
            await db2.execute(
                sa_delete(DocumentoGerado).where(
                    DocumentoGerado.id == uuid.UUID(doc_id),
                    DocumentoGerado.conteudo == "__PROCESSANDO__",
                )
            )
            await db2.commit()
        await engine2.dispose()
    except Exception as e:
        logger.warning(f"[OSINT-DEEP] Falha ao limpar placeholder: {e}")


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
