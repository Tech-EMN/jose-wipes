"""Authorize local Google Drive access and create the app folder."""

from __future__ import annotations

import json

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from scripts.config import GOOGLE_OAUTH_CLIENT_FILE, GOOGLE_OAUTH_TOKEN_FILE
from scripts.uploader import DRIVE_SCOPE, load_oauth_credentials, resolve_config_path


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
FOLDER_NAME = "José Wipes - Local"


def authorize_google_drive():
    credentials = load_oauth_credentials()
    token_path = resolve_config_path(GOOGLE_OAUTH_TOKEN_FILE)

    if credentials is None:
        client_path = resolve_config_path(GOOGLE_OAUTH_CLIENT_FILE)
        if not client_path.exists():
            raise FileNotFoundError(f"Cliente OAuth não encontrado: {client_path}")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_path),
            scopes=[DRIVE_SCOPE],
        )
        credentials = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")

    service = build("drive", "v3", credentials=credentials)
    query = (
        f"mimeType='{FOLDER_MIME_TYPE}' and "
        f"name='{FOLDER_NAME}' and trashed=false"
    )
    folders = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id,name,webViewLink)",
        pageSize=1,
    ).execute().get("files", [])

    if folders:
        folder = folders[0]
    else:
        folder = service.files().create(
            body={"name": FOLDER_NAME, "mimeType": FOLDER_MIME_TYPE},
            fields="id,name,webViewLink",
        ).execute()

    result = {
        "folder_id": folder["id"],
        "folder_link": folder.get(
            "webViewLink",
            f"https://drive.google.com/drive/folders/{folder['id']}",
        ),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    authorize_google_drive()
