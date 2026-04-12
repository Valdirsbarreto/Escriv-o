"""
Escrivão AI — Task Celery: Relatório Inicial de Investigação
Disparada quando todos os documentos de um inquérito estão indexados.

Fluxo:
1. Coleta resumos de todos os documentos + último aditamento do BO
2. LLM Premium gera Relatório Inicial estruturado (8 seções)
3. Salva como DocumentoGerado(tipo="relatorio_inicial") — 1ª peça na área de IA
4. Extrai e atualiza tipo_pessoa dos personagens (suspeito_principal, coautor, vitima,
   testemunha, policial_investigador, advogado, outro)
5. Atualiza Inquerito.descricao com o fato da Seção 1
6. Dispara generate_analise_task (síntese usa o relatório como contexto)
"""

import asyncio
import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Papéis válidos para tipo_pessoa
PAPEIS_VALIDOS = {
    "suspeito_principal", "coautor", "vitima", "testemunha",
    "policial_investigador", "advogado", "outro",
    # legado (mantidos para compatibilidade)
    "investigado",
}

# Regex para extrair seções do relatório
_RE_SECAO = re.compile(
    r"##\s*(\d+)\.\s*([^\n]+)\n(.*?)(?=##\s*\d+\.|$)",
    re.DOTALL,
)
# Regex para extrair nomes de linha "- **Nome**: ..."
_RE_PESSOA = re.compile(r"-\s*\*\*([^*]+)\*\*")


def _extrair_personagens_da_secao(texto_secao: str) -> list[str]:
    return [m.group(1).strip() for m in _RE_PESSOA.finditer(texto_secao)]


def _normalizar_nome(nome: str) -> str:
    import unicodedata
    nome = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", nome).strip().lower()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def gerar_relatorio_inicial_task(self, inquerito_id: str):
    """Gera o Relatório Inicial de Investigação para o inquérito."""
    logger.info(f"[REL-INICIAL] Iniciando — inquerito={inquerito_id}")

    async def _run():
        from app.models.inquerito import Inquerito
        from app.models.documento import Documento
        from app.models.pessoa import Pessoa
        from app.models.documento_gerado import DocumentoGerado
        from app.services.summary_service import SummaryService
        from app.services.llm_service import LLMService
        from app.core.prompts import PROMPT_RELATORIO_INICIAL, PROMPT_AUDITORIA_RELATORIO

        async_url = _encode_password_in_url(settings.DATABASE_URL)
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)

        import ssl
        connect_args = {"statement_cache_size": 0}
        if "supabase" in async_url or "localhost" not in async_url:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ctx

        from sqlalchemy.pool import NullPool
        engine = create_async_engine(async_url, connect_args=connect_args, poolclass=NullPool)
        AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        inq_uuid = uuid.UUID(inquerito_id)

        async with AsyncSession_() as db:
            inq = await db.get(Inquerito, inq_uuid)
            if not inq:
                logger.warning(f"[REL-INICIAL] Inquérito não encontrado: {inquerito_id}")
                await engine.dispose()
                return {"status": "inquerito_nao_encontrado"}

            # ── 1. Verificar se já existe relatório inicial ───────────────────
            existing = await db.execute(
                select(DocumentoGerado)
                .where(DocumentoGerado.inquerito_id == inq_uuid)
                .where(DocumentoGerado.tipo == "relatorio_inicial")
                .limit(1)
            )
            if existing.scalar_one_or_none():
                logger.info(f"[REL-INICIAL] Já existe relatório inicial — pulando")
                await engine.dispose()
                return {"status": "ja_existe"}

            # ── 2. Coletar resumos dos documentos ─────────────────────────────
            docs_result = await db.execute(
                select(Documento)
                .where(Documento.inquerito_id == inq_uuid)
                .where(Documento.status_processamento == "concluido")
                .where(Documento.tipo_peca != "sintese_investigativa")
            )
            todos_docs = docs_result.scalars().all()

            if not todos_docs:
                logger.warning(f"[REL-INICIAL] Sem docs indexados ainda: {inquerito_id}")
                raise Exception("sem_documentos_ainda")

            service = SummaryService()
            resumos_partes = []
            ultimo_aditamento = ""

            for d in todos_docs:
                r = await service.obter_resumo_documento(db, inq_uuid, d.id)
                texto = r or (d.texto_extraido[:2000] if d.texto_extraido else "")
                if not texto:
                    continue
                tipo = d.tipo_peca or "outro"
                resumos_partes.append(
                    f"**{d.nome_arquivo}** (tipo: {tipo})\n{texto}"
                )
                # Captura o último aditamento (mais recente)
                if tipo == "registro_aditamento" or "aditamento" in (d.nome_arquivo or "").lower():
                    ultimo_aditamento = d.texto_extraido[:3000] if d.texto_extraido else ""

            if not resumos_partes:
                raise Exception("sem_resumos_disponiveis")

            resumos_str = "\n\n---\n\n".join(resumos_partes)

            # ── 3. Personagens já no banco ────────────────────────────────────
            pessoas_result = await db.execute(
                select(Pessoa).where(Pessoa.inquerito_id == inq_uuid)
            )
            pessoas = pessoas_result.scalars().all()
            personagens_raw = "\n".join(
                f"- {p.nome} (CPF: {p.cpf or 'não informado'}) — tipo atual: {p.tipo_pessoa or 'não classificado'}"
                for p in pessoas
            ) or "Nenhum personagem identificado ainda."

            # ── 4. Chamar LLM Premium ─────────────────────────────────────────
            prompt = PROMPT_RELATORIO_INICIAL.format(
                resumos_documentos=resumos_str[:12000],
                ultimo_aditamento=ultimo_aditamento or "Não disponível.",
                personagens_raw=personagens_raw,
            )

            llm = LLMService()
            result_llm = await llm.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                tier="premium",
                temperature=0.15,
                max_tokens=4500,
                agente="RelatorioInicial",
            )
            relatorio_rascunho = result_llm["content"].strip()

            # ── 4b. Auditoria Anti-Alucinação (Agente Auditor) ───────────────
            relatorio_texto = relatorio_rascunho
            auditoria_log = ""
            try:
                prompt_auditoria = PROMPT_AUDITORIA_RELATORIO.format(
                    fontes_primarias=resumos_str[:10000],
                    relatorio_gerado=relatorio_rascunho,
                )
                result_auditoria = await llm.chat_completion(
                    messages=[{"role": "user", "content": prompt_auditoria}],
                    tier="standard",
                    temperature=0.0,
                    max_tokens=5000,
                    agente="AuditorRelatorio",
                )
                relatorio_auditado = result_auditoria["content"].strip()
                if relatorio_auditado:
                    relatorio_texto = relatorio_auditado
                    # Extrair bloco de auditoria para log
                    if "## AUDITORIA FACTUAL" in relatorio_auditado:
                        auditoria_log = relatorio_auditado.split("## AUDITORIA FACTUAL")[-1].strip()
                        logger.info(f"[REL-INICIAL] Auditoria factual:\n{auditoria_log}")
                    else:
                        logger.info("[REL-INICIAL] Auditoria concluída — sem marcadores de problema")
            except Exception as e_audit:
                logger.warning(f"[REL-INICIAL] Auditoria anti-alucinação falhou (usando rascunho): {e_audit}")
                relatorio_texto = relatorio_rascunho

            # ── 5. Salvar como DocumentoGerado ───────────────────────────────
            doc_gerado = DocumentoGerado(
                inquerito_id=inq_uuid,
                tipo="relatorio_inicial",
                titulo=f"Relatório Inicial de Investigação — {inq.numero}",
                conteudo=relatorio_texto,
                modelo_llm=result_llm.get("model"),
                tokens_prompt=result_llm.get("tokens_prompt"),
                tokens_resposta=result_llm.get("tokens_resposta"),
                custo_estimado=result_llm.get("custo_estimado"),
            )
            db.add(doc_gerado)
            await db.flush()

            # ── 6. Extrair e atualizar qualificação dos personagens ───────────
            secoes = {int(m.group(1)): m.group(3).strip() for m in _RE_SECAO.finditer(relatorio_texto)}

            mapa_papel = {
                2: "suspeito_principal",
                3: "coautor",
                4: "vitima",
                5: "testemunha",
                6: "policial_investigador",
            }

            # Constrói dicionário nome_normalizado → novo_papel
            qualificacoes: dict[str, str] = {}
            for secao_num, papel in mapa_papel.items():
                texto_secao = secoes.get(secao_num, "")
                for nome in _extrair_personagens_da_secao(texto_secao):
                    qualificacoes[_normalizar_nome(nome)] = papel

            # Atualiza pessoas no banco
            for p in pessoas:
                nome_norm = _normalizar_nome(p.nome)
                novo_papel = qualificacoes.get(nome_norm)
                if novo_papel and novo_papel != p.tipo_pessoa:
                    p.tipo_pessoa = novo_papel
                    logger.info(f"[REL-INICIAL] {p.nome} → {novo_papel}")

            # ── 7. Atualizar descricao do inquérito com Seção 1 ──────────────
            fato_secao = secoes.get(1, "")
            if fato_secao and len(fato_secao) > 20:
                # Usa as primeiras 3 linhas da seção 1 como descrição
                linhas = [l.strip() for l in fato_secao.split("\n") if l.strip()]
                descricao_nova = " ".join(linhas[:3])[:500]
                if descricao_nova:
                    inq.descricao = descricao_nova

            await db.commit()
            logger.info(f"[REL-INICIAL] Relatório salvo — {len(qualificacoes)} personagens qualificados")

        await engine.dispose()

        # ── 8. Disparar síntese (usa relatório como contexto) ─────────────
        try:
            from app.workers.summary_task import generate_analise_task
            generate_analise_task.delay(inquerito_id)
            logger.info(f"[REL-INICIAL] Síntese agendada — inquerito={inquerito_id}")
        except Exception as e:
            logger.warning(f"[REL-INICIAL] Falha ao agendar síntese: {e}")

        return {"status": "concluido", "inquerito_id": inquerito_id}

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info(f"[REL-INICIAL] Concluído — {result}")
        return result
    except Exception as e:
        logger.error(f"[REL-INICIAL] Erro: {e}")
        raise self.retry(exc=e)
