"""
Escrivão AI — Task Celery: Resumo Diário às 7h BRT
Envia todo dia às 10h UTC (7h BRT) um resumo do estado do sistema via Telegram.
Inclui semáforo: 🔴 problemas críticos | 🟡 atenção | 🟢 tudo ok.
"""

import logging
import re
from datetime import datetime, timedelta

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=0)
def resumo_diario_task(self):
    """Gera e envia resumo diário do sistema via Telegram (sem deduplicação)."""
    logger.info("[RESUMO-DIARIO] Gerando resumo diário do sistema")
    _executar_resumo()
    logger.info("[RESUMO-DIARIO] Concluído")


def _executar_resumo():
    from sqlalchemy import create_engine, and_, exists, select, func, not_
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from app.core.database import _encode_password_in_url
    from app.services.alerta_service import enviar_telegram_sync

    agora = datetime.utcnow()
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    limite_2h = agora - timedelta(hours=2)
    limite_6h = agora - timedelta(hours=6)

    engine = create_engine(
        _encode_password_in_url(settings.DATABASE_URL_SYNC),
        pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=300
    )
    Session = sessionmaker(bind=engine)

    try:
        with Session() as db:
            from app.models.inquerito import Inquerito
            from app.models.documento import Documento
            from app.models.documento_gerado import DocumentoGerado
            from app.models.consumo_api import ConsumoApi

            total_inqueritos = db.execute(select(func.count(Inquerito.id))).scalar() or 0

            docs_processando = db.execute(
                select(func.count(Documento.id)).where(Documento.status_processamento == "processando")
            ).scalar() or 0

            docs_erro = db.execute(
                select(func.count(Documento.id)).where(Documento.status_processamento == "erro")
            ).scalar() or 0

            gasto_mes = float(
                db.execute(
                    select(func.sum(ConsumoApi.custo_brl)).where(ConsumoApi.timestamp >= inicio_mes)
                ).scalar() or 0
            )

            # IPs travados: estado recebido/indexando + sem docs processados recentemente
            inqs_travados = db.execute(
                select(func.count(Inquerito.id)).where(
                    and_(
                        Inquerito.estado_atual.in_(["recebido", "indexando"]),
                        Inquerito.updated_at < limite_2h,
                    )
                )
            ).scalar() or 0

            # IPs sem relatório > 6h
            inqs_sem_relatorio = db.execute(
                select(func.count(Inquerito.id)).where(
                    and_(
                        Inquerito.updated_at < limite_6h,
                        exists(
                            select(Documento.id).where(
                                and_(
                                    Documento.inquerito_id == Inquerito.id,
                                    Documento.status_processamento == "concluido",
                                )
                            )
                        ),
                        not_(
                            exists(
                                select(Documento.id).where(
                                    and_(
                                        Documento.inquerito_id == Inquerito.id,
                                        Documento.status_processamento.in_(["pendente", "processando"]),
                                    )
                                )
                            )
                        ),
                        not_(
                            exists(
                                select(DocumentoGerado.id).where(
                                    and_(
                                        DocumentoGerado.inquerito_id == Inquerito.id,
                                        DocumentoGerado.tipo == "relatorio_inicial",
                                    )
                                )
                            )
                        ),
                    )
                )
            ).scalar() or 0

        # Semáforo
        limite_brl = float(settings.BUDGET_ALERT_BRL or settings.BUDGET_BRL or 0)
        if docs_erro > 0 or inqs_travados > 0:
            semaforo = "🔴"
            status_texto = "ATENÇÃO — há problemas para resolver"
        elif inqs_sem_relatorio > 0 or (limite_brl > 0 and gasto_mes >= limite_brl):
            semaforo = "🟡"
            status_texto = "Atenção recomendada"
        else:
            semaforo = "🟢"
            status_texto = "Sistema operando normalmente"

        data_str = agora.strftime("%d/%m/%Y")
        hora_str = agora.strftime("%H:%M UTC")

        mensagem_html = (
            f"{semaforo} <b>Escrivão AI — Resumo do dia {data_str}</b>\n"
            f"<i>{status_texto}</i>\n\n"
            f"<b>📁 Inquéritos:</b> {total_inqueritos} total\n"
            f"<b>⏳ Docs em processamento:</b> {docs_processando}\n"
            f"<b>❌ Docs com erro:</b> {docs_erro}\n"
            f"<b>🔒 IPs travados (> 2h):</b> {inqs_travados}\n"
            f"<b>📋 IPs sem relatório (> 6h):</b> {inqs_sem_relatorio}\n"
            f"<b>💰 Gasto LLM no mês:</b> R$ {gasto_mes:.2f}\n\n"
            f"<i>Gerado às {hora_str}</i>"
        )

        enviar_telegram_sync(mensagem_html)
        logger.info(
            f"[RESUMO-DIARIO] {semaforo} inq={total_inqueritos} "
            f"docs_err={docs_erro} travados={inqs_travados} sem_rel={inqs_sem_relatorio} "
            f"gasto=R${gasto_mes:.2f}"
        )

    except Exception as e:
        logger.error(f"[RESUMO-DIARIO] Erro ao gerar resumo: {e}")
    finally:
        engine.dispose()
