"""Upload de arquivos para Google Drive."""

import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import (
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_OAUTH_TOKEN_FILE,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    PROJECT_ROOT,
)


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def resolve_config_path(value):
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_oauth_credentials():
    token_path = resolve_config_path(GOOGLE_OAUTH_TOKEN_FILE)
    if not token_path.exists():
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=[DRIVE_SCOPE],
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials.valid:
        raise RuntimeError("Token OAuth do Google Drive inválido ou revogado.")
    return credentials


def load_drive_credentials():
    oauth_credentials = load_oauth_credentials()
    if oauth_credentials:
        return oauth_credentials

    from google.oauth2 import service_account

    service_account_path = resolve_config_path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not service_account_path.exists():
        raise FileNotFoundError("Credencial do Google Drive não encontrada.")
    return service_account.Credentials.from_service_account_file(
        str(service_account_path),
        scopes=[DRIVE_SCOPE],
    )


def upload_para_drive(arquivo_local, nome_arquivo=None, mimetype="video/mp4"):
    """Upload para Google Drive. Retorna {id, name, link} ou None."""
    arquivo_local = Path(arquivo_local)
    if nome_arquivo is None:
        nome_arquivo = arquivo_local.name

    if not GOOGLE_DRIVE_FOLDER_ID or GOOGLE_DRIVE_FOLDER_ID.startswith("your_"):
        log("GOOGLE_DRIVE_FOLDER_ID não configurado. Pulando upload.")
        return None

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = load_drive_credentials()
        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": nome_arquivo,
            "parents": [GOOGLE_DRIVE_FOLDER_ID],
        }

        media = MediaFileUpload(str(arquivo_local), mimetype=mimetype, resumable=True)

        log(f"Fazendo upload: {nome_arquivo}...")
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        ).execute()

        link = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{uploaded['id']}/view")
        log(f"✓ Upload OK: {link}")

        return {
            "id": uploaded["id"],
            "name": uploaded["name"],
            "link": link,
        }

    except Exception as e:
        log(f"✗ Erro no upload: {e}")
        return None
