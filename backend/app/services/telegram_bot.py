"""
Escrivão AI — Telegram Bot Service
Wrapper fino para a API do Telegram Bot (envio de mensagens, ações, configuração de webhook).
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _esc(text: str) -> str:
    """Escapa caracteres especiais HTML para uso em parse_mode=HTML."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TelegramBotService:
    """Realiza chamadas à API do Telegram Bot via httpx."""

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> dict:
        """Envia mensagem de texto. Trunca automaticamente ao limite do Telegram (4096 chars).
        Se o HTML for inválido (400 'can't parse entities'), re-envia como texto plano."""
        if len(text) > 4090:
            text = text[:4087] + "..."
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                payload: dict = {"chat_id": chat_id, "text": text}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                r = await client.post(self._url("sendMessage"), json=payload)
                result = r.json()
                # Telegram retorna HTTP 200 mesmo em erro lógico (ok=false)
                if not result.get("ok") and parse_mode:
                    desc = result.get("description", "")
                    if "parse" in desc.lower() or "entity" in desc.lower() or "can't" in desc.lower():
                        # HTML inválido → re-enviar sem parse_mode (texto plano)
                        logger.warning(f"[TELEGRAM] HTML inválido — re-enviando como texto plano: {desc}")
                        r2 = await client.post(
                            self._url("sendMessage"),
                            json={"chat_id": chat_id, "text": text},
                        )
                        return r2.json()
                return result
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro ao enviar mensagem: {e}")
                return {"ok": False, "error": str(e)}

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> dict:
        """Exibe indicador de ação (ex: 'digitando...')."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.post(
                    self._url("sendChatAction"),
                    json={"chat_id": chat_id, "action": action},
                )
                return r.json()
            except Exception as e:
                logger.error(f"[TELEGRAM] Erro ao enviar chat action: {e}")
                return {"ok": False}

    async def set_webhook(self, url: str, secret: str = "") -> dict:
        """Registra URL de webhook no Telegram."""
        payload: dict = {"url": url}
        if secret:
            payload["secret_token"] = secret
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(self._url("setWebhook"), json=payload)
            result = r.json()
            logger.info(f"[TELEGRAM] setWebhook → {result}")
            return result

    async def delete_webhook(self) -> dict:
        """Remove o webhook (útil ao trocar para polling em desenvolvimento)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(self._url("deleteWebhook"), json={"drop_pending_updates": True})
            return r.json()

    async def get_me(self) -> dict:
        """Retorna informações do bot (útil para verificar token)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(self._url("getMe"))
            return r.json()

    async def get_file(self, file_id: str) -> dict:
        """Obtém metadados de um arquivo (retorna file_path para download)."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(self._url("getFile"), json={"file_id": file_id})
            return r.json()

    async def download_file(self, file_path: str) -> bytes:
        """Baixa o conteúdo de um arquivo pelo file_path retornado em getFile."""
        url = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
