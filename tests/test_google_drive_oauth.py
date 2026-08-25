import os
import stat
from unittest.mock import MagicMock, patch

from scripts import uploader
from scripts.google_drive_auth import _write_oauth_token


def test_oauth_credentials_are_preferred():
    oauth_credentials = object()

    with (
        patch.object(
            uploader,
            "load_oauth_credentials",
            return_value=oauth_credentials,
        ),
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_file"
        ) as service_account_loader,
    ):
        credentials = uploader.load_drive_credentials()

    assert credentials is oauth_credentials
    service_account_loader.assert_not_called()


def test_expired_oauth_credentials_are_refreshed(tmp_path):
    token_path = tmp_path / "oauth-token.json"
    token_path.write_text("{}", encoding="utf-8")
    credentials = MagicMock(expired=True, refresh_token="refresh-token", valid=True)
    request = object()

    with patch.object(
        uploader,
        "GOOGLE_OAUTH_TOKEN_FILE",
        str(token_path),
    ), patch(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        return_value=credentials,
    ), patch(
        "google.auth.transport.requests.Request",
        return_value=request,
    ):
        result = uploader.load_oauth_credentials()

    assert result is credentials
    credentials.refresh.assert_called_once_with(request)


def test_service_account_is_fallback_when_oauth_is_missing(tmp_path):
    service_account_path = tmp_path / "service-account.json"
    service_account_path.write_text("{}", encoding="utf-8")
    service_account_credentials = object()

    with patch.object(
        uploader,
        "load_oauth_credentials",
        return_value=None,
    ), patch.object(
        uploader,
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(service_account_path),
    ), patch(
        "google.oauth2.service_account.Credentials.from_service_account_file",
        return_value=service_account_credentials,
    ) as service_account_loader:
        result = uploader.load_drive_credentials()

    assert result is service_account_credentials
    service_account_loader.assert_called_once_with(
        str(service_account_path),
        scopes=[uploader.DRIVE_SCOPE],
    )


def test_oauth_token_is_written_atomically_with_restricted_mode(tmp_path):
    token_path = tmp_path / "credentials" / "oauth-token.json"

    _write_oauth_token(token_path, '{"refresh_token":"secret"}')

    assert token_path.read_text(encoding="utf-8") == '{"refresh_token":"secret"}'
    assert not list(token_path.parent.glob(f".{token_path.name}.*"))
    if os.name != "nt":
        assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
