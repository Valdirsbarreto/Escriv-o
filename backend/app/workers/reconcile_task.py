"""
Escrivão AI — Task Celery: Reconciliação de Pipeline
Varre o banco periodicamente e re-despacha tasks interrompidas por:
  - rolling deploy do Railway (mata worker no meio da task)
  - crash do worker
  - falha de rede transitória
  - exception não capturada antes dos .delay()

Executada automaticamente a cada 15 min pelo Celery Beat.
Também disponível via endpoint admin: POST /ingestao/admin/pipeline/reconciliar

Invariantes de segurança:
  - Grace period de 15 min antes de re-despachar docs (evita re-dispatch de tasks em andamento)
  - Grace period de 30 min para relatório inicial / síntese
  - Cada sub-task tem lógica de idempotência própria (verifica se já existe antes de gerar)
  - Placeholder __PROCESSANDO__ travado > 30 min → removido e re-despachado
"""

import logging
import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, aliased

from app.core.config import settings
from app.core.database import _encode_password_in_url
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Grace periods — quanto tempo esperar antes de concluir que a task morreu
GRACE_DOCS = timedelta(minutes=15)
GRACE_RELATORIO = timedelta(minutes=30)
GRACE_SINTESE = timedelta(minutes=30)


def _build_sync_engine():
    raw_url = settings.DATABASE_URL
    sync_url = re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql://", raw_url)
    return create_engine(
        _encode_password_in_url(sync_url),
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=300,
    )


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60)
def reconcile_pipeline_task(self):
    """
    Verifica o banco de dados e re-despacha tasks de pipeline interrompidas.
    Executada automaticamente a cada 15 min pelo Celery Beat.

    Etapas verificadas (em ordem):
      1. Docs concluídos sem peças extraídas  → extrair_pecas_task
      2. Docs concluídos sem resumo           → generate_summaries_task
      3. Inquéritos prontos sem relatório     → gerar_relatorio_inicial_task
      4. Relatórios prontos sem síntese       → generate_analise_task
    """
    logger.info("[RECONCILE] ── Iniciando varredura de pipeline ──")

    engine = _build_sync_engine()
    SessionLocal = sessionmaker(bind=engine)

    stats = {
        "pecas_redespachadas": 0,
        "resumos_redespachados": 0,
        "relatorios_redespachados": 0,
        "sinteses_redespachadas": 0,
        "placeholders_removidos": 0,
    }

    with SessionLocal() as db:
        agora = datetime.utcnow()
        limite_docs = agora - GRACE_DOCS
        limite_relatorio = agora - GRACE_RELATORIO
        limite_sintese = agora - GRACE_SINTESE

        from app.models.documento import Documento
        from app.models.peca_extraida import PecaExtraida
        from app.models.resumo_cache import ResumoCache
        from app.models.documento_gerado import DocumentoGerado
        from app.models.inquerito import Inquerito

        # ── 1. Docs sem peças extraídas ──────────────────────────────────────
        # Condições: status=concluido, texto suficiente, sem PecaExtraida, age > 15min
        docs_sem_pecas = db.execute(
            select(Documento)
            .where(
                and_(
                    Documento.status_processamento == "concluido",
                    Documento.created_at < limite_docs,
                    func.length(Documento.texto_extraido) > 100,
                    ~exists(
                        select(PecaExtraida.id).where(
                            PecaExtraida.documento_id == Documento.id
                        )
                    ),
                )
            )
        ).scalars().all()

        if docs_sem_pecas:
            logger.info(f"[RECONCILE] {len(docs_sem_pecas)} doc(s) sem peças extraídas — re-despachando")
            from app.workers.peca_extraction_task import extrair_pecas_task
            for doc in docs_sem_pecas:
                logger.info(f"[RECONCILE]   → extrair_pecas_task doc={doc.id}")
                extrair_pecas_task.delay(str(doc.id), str(doc.inquerito_id))
                stats["pecas_redespachadas"] += 1

        # ── 2. Docs sem resumo de documento ──────────────────────────────────
        # Condições: status=concluido, sem ResumoCache(nivel='documento'), age > 15min
        docs_sem_resumo = db.execute(
            select(Documento)
            .where(
                and_(
                    Documento.status_processamento == "concluido",
                    Documento.created_at < limite_docs,
                    ~exists(
                        select(ResumoCache.id).where(
                            and_(
                                ResumoCache.referencia_id == Documento.id,
                                ResumoCache.nivel == "documento",
                            )
                        )
                    ),
                )
            )
        ).scalars().all()

        if docs_sem_resumo:
            logger.info(f"[RECONCILE] {len(docs_sem_resumo)} doc(s) sem resumo — re-despachando")
            from app.workers.summary_task import generate_summaries_task
            for doc in docs_sem_resumo:
                logger.info(f"[RECONCILE]   → generate_summaries_task doc={doc.id}")
                generate_summaries_task.delay(str(doc.inquerito_id), str(doc.id))
                stats["resumos_redespachados"] += 1

        # ── 3. Placeholder de relatório inicial travado (> 30 min) ──────────
        # Se um worker morreu depois de criar o placeholder, o campo fica preso
        # como __PROCESSANDO__ para sempre. Remove e re-despacha.
        placeholders_travados = db.execute(
            select(DocumentoGerado)
            .where(
                and_(
                    DocumentoGerado.tipo == "relatorio_inicial",
                    DocumentoGerado.conteudo == "__PROCESSANDO__",
                    DocumentoGerado.updated_at < limite_relatorio,
                )
            )
        ).scalars().all()

        for placeholder in placeholders_travados:
            minutos_preso = int((agora - placeholder.updated_at).total_seconds() / 60)
            logger.warning(
                f"[RECONCILE] Placeholder travado removido — inq={placeholder.inquerito_id} "
                f"(preso desde {placeholder.updated_at.strftime('%H:%M')} UTC)"
            )
            db.delete(placeholder)
            stats["placeholders_removidos"] += 1
            try:
                from app.services.alerta_service import enviar_alerta_sync, msg_placeholder_travado
                titulo, mensagem, mensagem_html = msg_placeholder_travado(str(placeholder.inquerito_id), minutos_preso)
                enviar_alerta_sync(
                    "docs_stuck_reconcile", "alerta", titulo, mensagem, mensagem_html,
                    identificador=str(placeholder.inquerito_id)
                )
            except Exception as _ae:
                logger.warning(f"[RECONCILE] Falha ao enviar alerta placeholder: {_ae}")
        db.commit()

        # ── 4. Inquéritos com todos os docs concluídos mas sem relatório inicial ──
        # Condição: todos os docs concluídos há > 30 min, sem DocumentoGerado(tipo='relatorio_inicial')
        inqueritos_sem_relatorio = db.execute(
            select(Inquerito.id)
            .where(
                and_(
                    # Tem ao menos 1 doc concluído com age > 30 min
                    exists(
                        select(Documento.id).where(
                            and_(
                                Documento.inquerito_id == Inquerito.id,
                                Documento.status_processamento == "concluido",
                                Documento.created_at < limite_relatorio,
                            )
                        )
                    ),
                    # Não tem docs em processamento
                    ~exists(
                        select(Documento.id).where(
                            and_(
                                Documento.inquerito_id == Inquerito.id,
                                Documento.status_processamento.in_(["pendente", "processando"]),
                            )
                        )
                    ),
                    # Não tem relatorio_inicial (nem placeholder — que foram limpos acima)
                    ~exists(
                        select(DocumentoGerado.id).where(
                            and_(
                                DocumentoGerado.inquerito_id == Inquerito.id,
                                DocumentoGerado.tipo == "relatorio_inicial",
                            )
                        )
                    ),
                )
            )
        ).scalars().all()

        if inqueritos_sem_relatorio:
            logger.info(
                f"[RECONCILE] {len(inqueritos_sem_relatorio)} inquérito(s) "
                "sem relatório inicial — re-despachando"
            )
            from app.workers.relatorio_inicial_task import gerar_relatorio_inicial_task
            for inq_id in inqueritos_sem_relatorio:
                logger.info(f"[RECONCILE]   → gerar_relatorio_inicial_task inq={inq_id}")
                gerar_relatorio_inicial_task.delay(str(inq_id))
                stats["relatorios_redespachados"] += 1

        # ── 5. Inquéritos com relatório inicial mas sem síntese ──────────────
        # Síntese é salva como Documento(tipo_peca='sintese_investigativa'), não DocumentoGerado.
        # generate_analise_task não usa placeholder — se não existe, foi interrompida antes de salvar.
        from app.models.documento import Documento as _Documento

        DG_rel = aliased(DocumentoGerado)
        Doc_sint = aliased(_Documento)

        inqueritos_sem_sintese = db.execute(
            select(DG_rel.inquerito_id)
            .where(
                and_(
                    DG_rel.tipo == "relatorio_inicial",
                    DG_rel.conteudo != "__PROCESSANDO__",
                    DG_rel.updated_at < limite_sintese,
                    ~exists(
                        select(Doc_sint.id).where(
                            and_(
                                Doc_sint.inquerito_id == DG_rel.inquerito_id,
                                Doc_sint.tipo_peca == "sintese_investigativa",
                            )
                        )
                    ),
                )
            )
        ).scalars().all()

        if inqueritos_sem_sintese:
            logger.info(
                f"[RECONCILE] {len(inqueritos_sem_sintese)} inquérito(s) "
                "com relatório mas sem síntese — re-despachando"
            )
            from app.workers.summary_task import generate_analise_task
            for inq_id in inqueritos_sem_sintese:
                logger.info(f"[RECONCILE]   → generate_analise_task inq={inq_id}")
                generate_analise_task.delay(str(inq_id))
                stats["sinteses_redespachadas"] += 1

    total_redespachadas = sum(v for k, v in stats.items() if "redesp" in k)
    if total_redespachadas == 0 and stats["placeholders_removidos"] == 0:
        logger.info("[RECONCILE] Tudo OK — nenhuma task interrompida encontrada")
    else:
        logger.info(
            f"[RECONCILE] Concluído — "
            f"peças={stats['pecas_redespachadas']} "
            f"resumos={stats['resumos_redespachados']} "
            f"relatórios={stats['relatorios_redespachados']} "
            f"sínteses={stats['sinteses_redespachadas']} "
            f"placeholders_removidos={stats['placeholders_removidos']}"
        )

    return stats
