"""Upload de arquivos para Google Drive."""

import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_DRIVE_FOLDER_ID, PROJECT_ROOT


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}")


def upload_para_drive(arquivo_local, nome_arquivo=None, mimetype="video/mp4"):
    """Upload para Google Drive. Retorna {id, name, link} ou None."""
    arquivo_local = Path(arquivo_local)
    if nome_arquivo is None:
        nome_arquivo = arquivo_local.name

    # Verificar configuração
    sa_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not sa_path.is_absolute():
        sa_path = PROJECT_ROOT / sa_path

    if not sa_path.exists():
        log("Google Drive não configurado (service account não encontrada). Pulando upload.")
        return None

    if not GOOGLE_DRIVE_FOLDER_ID or GOOGLE_DRIVE_FOLDER_ID.startswith("your_"):
        log("GOOGLE_DRIVE_FOLDER_ID não configurado. Pulando upload.")
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = service_account.Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
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
        ).execute()

        # Tentar tornar acessível por link
        try:
            service.permissions().create(
                fileId=uploaded["id"],
                body={"role": "reader", "type": "anyone"},
            ).execute()
        except Exception:
            pass  # Permissão pode falhar, não é crítico

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
