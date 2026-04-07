"""
Escrivão AI — Script: Autorização Google Calendar (executar UMA vez)

Este script abre o navegador para você autorizar o acesso ao Google Agenda.
Ao concluir, exibe o refresh_token que deve ser salvo no .env.

Pré-requisitos:
  1. Criar um projeto no Google Cloud Console: https://console.cloud.google.com/
  2. Ativar a API "Google Calendar API"
  3. Criar credenciais OAuth2 (tipo: "Aplicativo de desktop")
  4. Baixar o JSON de credenciais
  5. Instalar dependências: pip install google-auth-oauthlib

Uso:
  python backend/scripts/google_calendar_auth.py --credentials path/para/client_secret.json

Após rodar, adicione ao .env:
  GOOGLE_CLIENT_ID=...
  GOOGLE_CLIENT_SECRET=...
  GOOGLE_CALENDAR_REFRESH_TOKEN=...
  GOOGLE_CALENDAR_ID=primary
"""

import argparse
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    parser = argparse.ArgumentParser(description="Autorização Google Calendar para o Escrivão AI")
    parser.add_argument(
        "--credentials",
        required=True,
        help="Caminho para o arquivo client_secret_*.json baixado do Google Cloud Console",
    )
    args = parser.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERRO: Instale google-auth-oauthlib primeiro:")
        print("  pip install google-auth-oauthlib")
        sys.exit(1)

    print("\n=== Escrivão AI — Autorização Google Calendar ===\n")
    print("Uma janela do navegador será aberta para você autorizar o acesso.")
    print("Faça login na conta Google onde está o calendário que deseja usar.\n")

    flow = InstalledAppFlow.from_client_secrets_file(args.credentials, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nAutorizacao concluida!\n")
    print("Adicione as seguintes variaveis ao seu .env:\n")

    with open(args.credentials) as f:
        client_data = json.load(f)

    # Suporta tanto formato "installed" quanto "web"
    client_info = client_data.get("installed") or client_data.get("web", {})
    client_id = client_info.get("client_id", "")
    client_secret = client_info.get("client_secret", "")

    print(f"GOOGLE_CLIENT_ID={client_id}")
    print(f"GOOGLE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={creds.refresh_token}")
    print("GOOGLE_CALENDAR_ID=primary")
    print()
    print("Nota: 'primary' usa o calendario principal da conta.")
    print("Para usar um calendario especifico, substitua pelo ID do calendario.")


if __name__ == "__main__":
    main()
