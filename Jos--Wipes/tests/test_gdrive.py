"""Testa autenticação e upload para Google Drive."""

import sys
import tempfile
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from scripts.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_DRIVE_FOLDER_ID, PROJECT_ROOT
from pathlib import Path


def main():
    print("=" * 50)
    print("TESTE: Google Drive — Upload")
    print("=" * 50)

    # [1/5] Verificar service account
    print("\n[1/5] Verificando service account...")
    sa_path = Path(GOOGLE_SERVICE_ACCOUNT_FILE)
    if not sa_path.is_absolute():
        sa_path = PROJECT_ROOT / sa_path

    if not sa_path.exists():
        print(f"  ✗ Arquivo service account não encontrado: {sa_path}")
        print(f"  Instruções:")
        print(f"    1. Vá em console.cloud.google.com")
        print(f"    2. IAM & Admin → Service Accounts → Create")
        print(f"    3. Baixe o JSON e coloque em: {PROJECT_ROOT / 'credentials' / 'google-service-account.json'}")
        return 1
    print(f"  ✓ Service account: {sa_path}")

    # [2/5] Verificar folder ID
    print("\n[2/5] Verificando GOOGLE_DRIVE_FOLDER_ID...")
    if not GOOGLE_DRIVE_FOLDER_ID or GOOGLE_DRIVE_FOLDER_ID.startswith("your_"):
        print("  ✗ GOOGLE_DRIVE_FOLDER_ID não configurado no .env")
        return 1
    print(f"  ✓ Folder ID: {GOOGLE_DRIVE_FOLDER_ID}")

    # [3/5] Autenticar
    print("\n[3/5] Autenticando com service account...")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            str(sa_path),
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)
        print("  ✓ Autenticação OK")
    except Exception as e:
        print(f"  ✗ Erro de autenticação: {e}")
        return 1

    # [4/5] Criar arquivo de teste
    print("\n[4/5] Criando e fazendo upload de arquivo de teste...")
    try:
        from googleapiclient.http import MediaFileUpload

        # Criar arquivo temporário
        test_file = PROJECT_ROOT / "output" / "teste_gdrive.txt"
        test_file.write_text(
            "Teste do pipeline José Wipes.\nSe você vê este arquivo, o upload está funcionando!",
            encoding="utf-8"
        )

        file_metadata = {
            "name": "teste_jose_wipes_pipeline.txt",
            "parents": [GOOGLE_DRIVE_FOLDER_ID],
        }
        media = MediaFileUpload(str(test_file), mimetype="text/plain")

        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        ).execute()

        print(f"  ✓ Upload OK!")

    except Exception as e:
        print(f"  ✗ Erro no upload: {e}")
        if "notFound" in str(e) or "404" in str(e):
            print(f"\n  Provável causa: pasta não compartilhada com a service account.")
            print(f"  No Google Drive, compartilhe a pasta com o email da service account")
            print(f"  (encontrado no JSON da service account, campo 'client_email').")
        return 1

    # [5/5] Mostrar resultado
    print(f"\n[5/5] Resultado:")
    print(f"  ✓ ID: {uploaded.get('id')}")
    print(f"  ✓ Nome: {uploaded.get('name')}")
    link = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{uploaded.get('id')}/view")
    print(f"  ✓ Link: {link}")

    print(f"\n{'=' * 50}")
    print("  ✓ TESTE GOOGLE DRIVE: PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
