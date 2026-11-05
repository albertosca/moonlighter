"""The interactive OAuth flow that writes the token."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.tracking.gmail.client import GmailAuthError, run_gmail_oauth


def test_gmail_oauth_sets_chmod_600_on_token(tmp_path):
    token_path = str(tmp_path / "subdir" / "gmail-token.json")
    credentials_path = str(tmp_path / "creds.json")

    mock_credentials = MagicMock()
    mock_credentials.to_json.return_value = '{"token": "abc"}'

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch("moonlighter.tracking.gmail.client.InstalledAppFlow") as flow_class:
        flow_class.from_client_secrets_file.return_value = mock_flow
        run_gmail_oauth(credentials_path, token_path)

    written = Path(token_path)
    assert written.read_text() == '{"token": "abc"}'
    assert written.stat().st_mode & 0o777 == 0o600


def testrun_gmail_oauth_raises_without_oauthlib():
    """InstalledAppFlow None → GmailAuthError (454)."""
    with (
        patch("moonlighter.tracking.gmail.client.InstalledAppFlow", None),
        pytest.raises(GmailAuthError, match="google-auth-oauthlib"),
    ):
        run_gmail_oauth("creds.json", "token.json")
