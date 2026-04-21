"""
Escrivão AI — Serviço de Alertas
Centralizador de alertas do sistema: deduplicação Redis + templates + persistência DB + envio Telegram.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# TTLs de deduplicação por tipo (segundos)
_DEDUP_TTL = {
    "task_failure": 3600,           # 1h
    "doc_stuck": 7200,              # 2h
    "docs_stuck_reconcile": 7200,   # 2h
    "budget_alerta": 43200,         # 12h
    "budget_critico": 21600,        # 6h
    "egress_supabase": 86400,       # 24h
    "inquerito_sem_relatorio": 21600,  # 6h
    "heartbeat_ausente": 7200,      # 2h
}
_DEFAULT_TTL = 3600


# ── Deduplicação via Redis ─────────────────────────────────────────────────────

def ja_alertado(tipo: str, identificador: str = "") -> bool:
    """
    Verifica se este alerta já foi enviado recentemente via Redis SET NX.
    Retorna True se deve suprimir (já alertado dentro do TTL).
    """
    try:
        from app.core.config import settings
        import redis as redis_lib

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"escrivao:alerta:{tipo}:{identificador}" if identificador else f"escrivao:alerta:{tipo}"
        ttl = _DEDUP_TTL.get(tipo, _DEFAULT_TTL)
        result = r.set(key, "1", nx=True, ex=ttl)
        # set retorna True se gravou (chave nova = NÃO alertado antes)
        # set retorna None se chave já existia (alertado recentemente = suprimir)
        return result is None
    except Exception as e:
        logger.warning(f"[ALERTA] Redis dedup falhou — enviando sem dedup: {e}")
        return False  # na dúvida, permite envio


# ── Envio Telegram ─────────────────────────────────────────────────────────────

def enviar_telegram_sync(mensagem_html: str) -> None:
    """Envia mensagem para todos os TELEGRAM_ALLOWED_USER_IDS via httpx síncrono."""
    from app.core.config import settings

    token = settings.TELEGRAM_BOT_TOKEN
    user_ids_raw = settings.TELEGRAM_ALLOWED_USER_IDS or ""
    if not token or not user_ids_raw:
        return

    user_ids = [uid.strip() for uid in user_ids_raw.split(",") if uid.strip().isdigit()]
    try:
        with httpx.Client(timeout=8.0) as client:
            for uid in user_ids:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": uid, "text": mensagem_html, "parse_mode": "HTML"},
                )
                if resp.status_code == 400:
                    # HTML parse error — tenta texto plano
                    texto_limpo = re.sub(r"<[^>]+>", "", mensagem_html)
                    client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": uid, "text": texto_limpo},
                    )
    except Exception as e:
        logger.warning(f"[ALERTA] Falha ao enviar Telegram sync: {e}")


async def enviar_telegram_async(mensagem_html: str) -> None:
    """Envia mensagem para todos os TELEGRAM_ALLOWED_USER_IDS via TelegramBotService async."""
    try:
        from app.services.telegram_bot import TelegramBotService
        from app.core.config import settings

        user_ids_raw = settings.TELEGRAM_ALLOWED_USER_IDS or ""
        user_ids = [uid.strip() for uid in user_ids_raw.split(",") if uid.strip().isdigit()]
        for uid in user_ids:
            await TelegramBotService.send_message(uid, mensagem_html)
    except Exception as e:
        logger.warning(f"[ALERTA] Falha ao enviar Telegram async: {e}")


# ── Persistência no banco ──────────────────────────────────────────────────────

def _salvar_alerta_db_sync(
    tipo: str,
    nivel: str,
    titulo: str,
    mensagem: str,
    mensagem_html: str,
    identificador: Optional[str] = None,
) -> None:
    """Insere AlertaLog usando engine síncrono (padrão dos workers Celery)."""
    try:
        import re as _re
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.core.database import _encode_password_in_url
        from app.models.alerta_log import AlertaLog

        engine = create_engine(
            _encode_password_in_url(settings.DATABASE_URL_SYNC),
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
        )
        Session = sessionmaker(bind=engine)
        with Session() as db:
            alerta = AlertaLog(
                id=uuid.uuid4(),
                tipo=tipo,
                nivel=nivel,
                titulo=titulo,
                mensagem=mensagem,
                mensagem_html=mensagem_html,
                identificador=identificador,
                lido=False,
                created_at=datetime.utcnow(),
            )
            db.add(alerta)
            db.commit()
        engine.dispose()
    except Exception as e:
        logger.error(f"[ALERTA] Falha ao salvar AlertaLog no banco: {e}")


async def _salvar_alerta_db_async(
    tipo: str,
    nivel: str,
    titulo: str,
    mensagem: str,
    mensagem_html: str,
    identificador: Optional[str] = None,
) -> None:
    """Insere AlertaLog usando sessão async (padrão dos routers FastAPI)."""
    try:
        from app.core.database import async_session
        from app.models.alerta_log import AlertaLog

        async with async_session() as db:
            alerta = AlertaLog(
                id=uuid.uuid4(),
                tipo=tipo,
                nivel=nivel,
                titulo=titulo,
                mensagem=mensagem,
                mensagem_html=mensagem_html,
                identificador=identificador,
                lido=False,
                created_at=datetime.utcnow(),
            )
            db.add(alerta)
            await db.commit()
    except Exception as e:
        logger.error(f"[ALERTA] Falha ao salvar AlertaLog (async) no banco: {e}")


# ── Envio central ──────────────────────────────────────────────────────────────

def enviar_alerta_sync(
    tipo: str,
    nivel: str,
    titulo: str,
    mensagem: str,
    mensagem_html: str,
    identificador: str = "",
) -> bool:
    """
    Envia alerta completo (dedup + DB + Telegram) de forma síncrona.
    Retorna True se enviou, False se suprimido por deduplicação.
    """
    if ja_alertado(tipo, identificador):
        logger.debug(f"[ALERTA] Suprimido por dedup: {tipo}/{identificador}")
        return False

    _salvar_alerta_db_sync(tipo, nivel, titulo, mensagem, mensagem_html, identificador or None)
    enviar_telegram_sync(mensagem_html)
    logger.info(f"[ALERTA] Enviado: {tipo} — {titulo}")
    return True


async def enviar_alerta_async(
    tipo: str,
    nivel: str,
    titulo: str,
    mensagem: str,
    mensagem_html: str,
    identificador: str = "",
) -> bool:
    """
    Envia alerta completo (dedup + DB + Telegram) de forma assíncrona.
    Retorna True se enviou, False se suprimido por deduplicação.
    """
    if ja_alertado(tipo, identificador):
        logger.debug(f"[ALERTA] Suprimido por dedup: {tipo}/{identificador}")
        return False

    await _salvar_alerta_db_async(tipo, nivel, titulo, mensagem, mensagem_html, identificador or None)
    await enviar_telegram_async(mensagem_html)
    logger.info(f"[ALERTA] Enviado (async): {tipo} — {titulo}")
    return True


# ── Templates de mensagem ──────────────────────────────────────────────────────

def msg_task_failure(
    label: str,
    erro_resumo: str,
    task_id: str,
    inq_info: str = "",
) -> tuple[str, str, str]:
    titulo = f"Falha na task: {label}"
    mensagem = (
        f"O que aconteceu: A task '{label}' falhou.\n"
        f"Erro: {erro_resumo}\n"
        f"Por que importa: O processamento do inquérito pode ter sido interrompido.\n"
        f"O que fazer agora: Verifique os logs do Railway ou tente reprocessar o documento.\n"
        f"Ref técnica: task_id={task_id[:16] if task_id else '?'}{inq_info}"
    )
    inq_html = f"\n🔑 Inquérito: <code>{inq_info}</code>" if inq_info else ""
    mensagem_html = (
        f"🔴 <b>Falha na task: {label}</b>\n\n"
        f"<b>O que aconteceu:</b> A task falhou com o erro:\n<code>{erro_resumo}</code>\n\n"
        f"<b>Por que importa:</b> O processamento do inquérito pode ter sido interrompido.{inq_html}\n\n"
        f"<b>O que fazer agora:</b> Verifique os logs no Railway ou tente reprocessar o documento.\n\n"
        f"<i>Ref técnica: task_id={task_id[:16] if task_id else '?'}</i>"
    )
    return titulo, mensagem, mensagem_html


def msg_doc_preso(
    inq_numero: str,
    doc_nome: str,
    minutos: int,
    doc_id: str,
) -> tuple[str, str, str]:
    titulo = f"Documento travado no processamento"
    mensagem = (
        f"O que aconteceu: O documento '{doc_nome}' do IP {inq_numero} "
        f"está em processamento há {minutos} minutos sem concluir.\n"
        f"Por que importa: O relatório do inquérito não será gerado enquanto houver documentos travados.\n"
        f"O que fazer agora: Acesse o painel admin e verifique se o worker Celery está rodando. "
        f"Se necessário, re-faça o upload do documento.\n"
        f"Ref técnica: doc_id={doc_id[:16]}"
    )
    mensagem_html = (
        f"🟡 <b>Documento travado no processamento</b>\n\n"
        f"<b>O que aconteceu:</b> O documento <i>{doc_nome}</i> do IP {inq_numero} "
        f"está em processamento há <b>{minutos} minutos</b> sem concluir.\n\n"
        f"<b>Por que importa:</b> O relatório do inquérito não será gerado enquanto houver documentos travados.\n\n"
        f"<b>O que fazer agora:</b> Verifique se o worker Celery está rodando no Railway. "
        f"Se necessário, re-faça o upload do documento.\n\n"
        f"<i>Ref técnica: doc_id={doc_id[:16]}</i>"
    )
    return titulo, mensagem, mensagem_html


def msg_placeholder_travado(inq_id: str, minutos: int) -> tuple[str, str, str]:
    titulo = f"Geração de relatório travada"
    mensagem = (
        f"O que aconteceu: A geração do relatório inicial de um inquérito "
        f"foi interrompida há {minutos} minutos (worker reiniciou no meio).\n"
        f"Por que importa: O inquérito ficará sem relatório até ser reprocessado.\n"
        f"O que fazer agora: O sistema tentará regenerar automaticamente em até 30 minutos. "
        f"Se o problema persistir, use o botão de regenerar relatório no inquérito.\n"
        f"Ref técnica: inq_id={inq_id[:16]}"
    )
    mensagem_html = (
        f"🟡 <b>Geração de relatório travada</b>\n\n"
        f"<b>O que aconteceu:</b> A geração do relatório inicial foi interrompida há <b>{minutos} minutos</b> "
        f"(o servidor reiniciou no meio da operação).\n\n"
        f"<b>Por que importa:</b> O inquérito ficará sem relatório até ser reprocessado.\n\n"
        f"<b>O que fazer agora:</b> O sistema tentará regenerar automaticamente. "
        f"Se o problema persistir após 30 min, use o botão de regenerar relatório.\n\n"
        f"<i>Ref técnica: inq_id={inq_id[:16]}</i>"
    )
    return titulo, mensagem, mensagem_html


def msg_inquerito_sem_relatorio(
    numero: str,
    horas: int,
    inq_id: str,
) -> tuple[str, str, str]:
    titulo = f"IP {numero} sem relatório há {horas}h"
    mensagem = (
        f"O que aconteceu: O IP {numero} tem todos os documentos processados "
        f"mas está sem relatório inicial há mais de {horas} horas.\n"
        f"Por que importa: Sem o relatório, o Copiloto não tem contexto completo do caso.\n"
        f"O que fazer agora: Acesse o inquérito e clique em 'Gerar Relatório Inicial'.\n"
        f"Ref técnica: inq_id={inq_id[:16]}"
    )
    mensagem_html = (
        f"🟡 <b>IP {numero} sem relatório há {horas}h</b>\n\n"
        f"<b>O que aconteceu:</b> O IP {numero} tem todos os documentos processados "
        f"mas está sem relatório inicial há mais de <b>{horas} horas</b>.\n\n"
        f"<b>Por que importa:</b> Sem o relatório, o Copiloto não tem contexto completo do caso.\n\n"
        f"<b>O que fazer agora:</b> Acesse o inquérito no Escrivão e clique em 'Gerar Relatório Inicial'.\n\n"
        f"<i>Ref técnica: inq_id={inq_id[:16]}</i>"
    )
    return titulo, mensagem, mensagem_html


def msg_budget_alerta(
    gasto_brl: float,
    limite_brl: float,
    pct: float,
) -> tuple[str, str, str]:
    titulo = f"Budget LLM em {pct:.0f}% do limite mensal"
    mensagem = (
        f"O que aconteceu: O gasto com IA este mês atingiu R$ {gasto_brl:.2f} "
        f"({pct:.0f}% do limite de R$ {limite_brl:.2f}).\n"
        f"Por que importa: Se ultrapassar o limite, as operações de IA podem ser interrompidas.\n"
        f"O que fazer agora: Monitore o painel administrativo. Evite reprocessamentos desnecessários."
    )
    mensagem_html = (
        f"🟡 <b>Budget LLM em {pct:.0f}% do limite mensal</b>\n\n"
        f"<b>O que aconteceu:</b> O gasto com IA este mês atingiu <b>R$ {gasto_brl:.2f}</b> "
        f"({pct:.0f}% do limite de R$ {limite_brl:.2f}).\n\n"
        f"<b>Por que importa:</b> Se ultrapassar o limite, as operações de IA podem ser interrompidas.\n\n"
        f"<b>O que fazer agora:</b> Monitore o painel administrativo. Evite reprocessamentos desnecessários."
    )
    return titulo, mensagem, mensagem_html


def msg_budget_critico(gasto_brl: float, limite_brl: float) -> tuple[str, str, str]:
    titulo = f"Budget LLM ESGOTADO — R$ {gasto_brl:.2f} de R$ {limite_brl:.2f}"
    mensagem = (
        f"O que aconteceu: O gasto com IA ultrapassou o limite mensal de R$ {limite_brl:.2f}.\n"
        f"Por que importa: Novas operações de IA podem ser bloqueadas até o próximo mês.\n"
        f"O que fazer agora: Acesse o painel admin e considere aumentar o limite ou aguardar a virada do mês."
    )
    mensagem_html = (
        f"🔴 <b>Budget LLM ESGOTADO</b>\n\n"
        f"<b>O que aconteceu:</b> O gasto com IA ultrapassou o limite mensal — "
        f"<b>R$ {gasto_brl:.2f}</b> de R$ {limite_brl:.2f}.\n\n"
        f"<b>Por que importa:</b> Novas operações de IA podem ser bloqueadas até o próximo mês.\n\n"
        f"<b>O que fazer agora:</b> Acesse o painel admin e considere aumentar o limite "
        f"ou aguardar a virada do mês."
    )
    return titulo, mensagem, mensagem_html


def msg_egress_supabase(egress_mb: float, limite_mb: float, pct: float) -> tuple[str, str, str]:
    titulo = f"Supabase egress em {pct:.0f}% do limite mensal"
    mensagem = (
        f"O que aconteceu: O tráfego de saída do banco de dados atingiu {egress_mb:.0f} MB "
        f"({pct:.0f}% do limite gratuito de {limite_mb:.0f} MB).\n"
        f"Por que importa: Se ultrapassar, o Supabase pode cobrar ou limitar o serviço.\n"
        f"O que fazer agora: Verifique no painel admin se há documentos sendo reprocessados "
        f"desnecessariamente. Considere o plano Pro do Supabase ($25/mês)."
    )
    mensagem_html = (
        f"🟡 <b>Supabase egress em {pct:.0f}% do limite mensal</b>\n\n"
        f"<b>O que aconteceu:</b> O tráfego de saída do banco atingiu <b>{egress_mb:.0f} MB</b> "
        f"({pct:.0f}% do limite gratuito de {limite_mb:.0f} MB).\n\n"
        f"<b>Por que importa:</b> Se ultrapassar, o Supabase pode cobrar ou limitar o serviço.\n\n"
        f"<b>O que fazer agora:</b> Verifique no painel admin se há documentos reprocessando "
        f"desnecessariamente. Considere o plano Pro do Supabase ($25/mês)."
    )
    return titulo, mensagem, mensagem_html


def msg_heartbeat_ausente(minutos: int) -> tuple[str, str, str]:
    titulo = f"Celery Beat não responde há {minutos} minutos"
    mensagem = (
        f"O que aconteceu: O serviço de tarefas agendadas (Celery Beat) "
        f"não registrou atividade há {minutos} minutos.\n"
        f"Por que importa: Alertas automáticos e reconciliação de pipeline ficam suspensos.\n"
        f"O que fazer agora: Verifique no Railway se o serviço está rodando. "
        f"Um reinício pode resolver o problema."
    )
    mensagem_html = (
        f"🔴 <b>Celery Beat não responde há {minutos} minutos</b>\n\n"
        f"<b>O que aconteceu:</b> O serviço de tarefas agendadas não registrou atividade "
        f"há <b>{minutos} minutos</b>.\n\n"
        f"<b>Por que importa:</b> Alertas automáticos e reconciliação de pipeline ficam suspensos.\n\n"
        f"<b>O que fazer agora:</b> Verifique no Railway se o serviço está rodando. "
        f"Um reinício do deploy pode resolver."
    )
    return titulo, mensagem, mensagem_html
