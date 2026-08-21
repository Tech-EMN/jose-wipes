from unittest.mock import patch

from scripts import uploader


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
