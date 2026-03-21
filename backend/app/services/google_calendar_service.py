"""
Escrivão AI — Serviço: Google Calendar
Cria, atualiza e remove eventos de oitivas no Google Agenda.
Usa OAuth2 com refresh token estático (single-user).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """
    Wrapper para a API do Google Calendar.

    Pré-requisito: executar `backend/scripts/google_calendar_auth.py` uma vez
    para obter o refresh token e preencher as variáveis no .env:
        GOOGLE_CLIENT_ID
        GOOGLE_CLIENT_SECRET
        GOOGLE_CALENDAR_REFRESH_TOKEN
        GOOGLE_CALENDAR_ID  (opcional, padrão: "primary")
    """

    def _build_service(self):
        """Constrói o serviço autenticado do Google Calendar."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not all([
            settings.GOOGLE_CLIENT_ID,
            settings.GOOGLE_CLIENT_SECRET,
            settings.GOOGLE_CALENDAR_REFRESH_TOKEN,
        ]):
            raise RuntimeError(
                "Google Calendar não configurado. "
                "Defina GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET e "
                "GOOGLE_CALENDAR_REFRESH_TOKEN no .env. "
                "Execute backend/scripts/google_calendar_auth.py para obter o token."
            )

        creds = Credentials(
            token=None,
            refresh_token=settings.GOOGLE_CALENDAR_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def criar_evento_oitiva(
        self,
        intimado_nome: str,
        data_oitiva: datetime,
        numero_inquerito: Optional[str] = None,
        local_oitiva: Optional[str] = None,
        qualificacao: Optional[str] = None,
        duracao_minutos: int = 60,
    ) -> dict:
        """
        Cria um evento no Google Agenda para a oitiva.

        Retorna:
            {"event_id": str, "event_url": str}
        """
        service = self._build_service()
        calendar_id = settings.GOOGLE_CALENDAR_ID

        qual_label = qualificacao or "oitiva"
        inq_label = f" — IP {numero_inquerito}" if numero_inquerito else ""
        titulo = f"Oitiva: {intimado_nome} ({qual_label}){inq_label}"

        descricao_partes = [f"Intimado: {intimado_nome}"]
        if qualificacao:
            descricao_partes.append(f"Qualificação: {qualificacao}")
        if numero_inquerito:
            descricao_partes.append(f"Inquérito: {numero_inquerito}")
        if local_oitiva:
            descricao_partes.append(f"Local: {local_oitiva}")
        descricao_partes.append("\nAgendado automaticamente pelo Escrivão AI.")
        descricao = "\n".join(descricao_partes)

        fim = data_oitiva + timedelta(minutes=duracao_minutos)

        evento = {
            "summary": titulo,
            "description": descricao,
            "location": local_oitiva or "",
            "start": {
                "dateTime": data_oitiva.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "end": {
                "dateTime": fim.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                    {"method": "popup", "minutes": 1440},  # 1 dia antes
                ],
            },
        }

        criado = service.events().insert(calendarId=calendar_id, body=evento).execute()
        logger.info(f"[GCAL] Evento criado: {criado.get('id')} — {titulo}")

        return {
            "event_id": criado.get("id"),
            "event_url": criado.get("htmlLink"),
        }

    def atualizar_evento_oitiva(
        self,
        event_id: str,
        intimado_nome: str,
        data_oitiva: datetime,
        numero_inquerito: Optional[str] = None,
        local_oitiva: Optional[str] = None,
        qualificacao: Optional[str] = None,
        duracao_minutos: int = 60,
    ) -> dict:
        """Atualiza um evento existente no Google Agenda."""
        service = self._build_service()
        calendar_id = settings.GOOGLE_CALENDAR_ID

        qual_label = qualificacao or "oitiva"
        inq_label = f" — IP {numero_inquerito}" if numero_inquerito else ""
        titulo = f"Oitiva: {intimado_nome} ({qual_label}){inq_label}"

        fim = data_oitiva + timedelta(minutes=duracao_minutos)

        evento = {
            "summary": titulo,
            "location": local_oitiva or "",
            "start": {
                "dateTime": data_oitiva.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "end": {
                "dateTime": fim.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
        }

        atualizado = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=evento)
            .execute()
        )
        logger.info(f"[GCAL] Evento atualizado: {event_id}")
        return {
            "event_id": atualizado.get("id"),
            "event_url": atualizado.get("htmlLink"),
        }

    def cancelar_evento(self, event_id: str) -> None:
        """Remove um evento do Google Agenda."""
        service = self._build_service()
        service.events().delete(
            calendarId=settings.GOOGLE_CALENDAR_ID, eventId=event_id
        ).execute()
        logger.info(f"[GCAL] Evento removido: {event_id}")
