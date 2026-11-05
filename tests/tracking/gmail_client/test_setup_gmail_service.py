"""Building the Gmail service from the token: paths, refresh and missing pieces."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.tracking.gmail_client import GmailAuthError, setup_gmail_service


def test_returns_service_when_token_exists(tmp_path):
    token_path = str(tmp_path / "gmail-token.json")
    credentials_path = str(tmp_path / "gmail-client.json")

    mock_credentials = MagicMock()
    mock_credentials.valid = True
    mock_credentials.expired = False

    config = {
        "email": {
            "credentials_path": credentials_path,
            "token_path": token_path,
        }
    }

    with (
        patch("moonlighter.tracking.gmail_client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail_client.build") as mock_build,
        patch("os.path.exists", return_value=True),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()

        service = setup_gmail_service(config)

    assert service is not None
    mock_build.assert_called_once_with("gmail", "v1", credentials=mock_credentials)


def test_resolves_a_relative_token_path_under_moonlighter_home(tmp_path, monkeypatch):
    """IMPORTANT 6: token_path defaults to a relative filename now
    ("gmail-token.json"), and setup_gmail_service must resolve it under
    MOONLIGHTER_HOME rather than treating it as relative to the cwd.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "gmail-token.json").write_text("{}")

    mock_credentials = MagicMock(valid=True, expired=False)
    config = {"email": {"token_path": "gmail-token.json"}}

    with (
        patch("moonlighter.tracking.gmail_client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail_client.build") as mock_build,
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()
        setup_gmail_service(config)

    credentials_class.from_authorized_user_file.assert_called_once()
    called_path = credentials_class.from_authorized_user_file.call_args.args[0]
    assert called_path == str(tmp_path / "gmail-token.json")


def test_refreshed_token_is_persisted_when_the_file_is_ours(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    token_path = tmp_path / "gmail-token.json"
    token_path.write_text("{}")

    mock_credentials = MagicMock(valid=False, expired=True, refresh_token="r")
    mock_credentials.to_json.return_value = '{"token": "novo"}'
    config = {"email": {"token_path": str(token_path)}}

    with (
        patch("moonlighter.tracking.gmail_client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail_client.build"),
        patch("moonlighter.tracking.gmail_client.Request"),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        setup_gmail_service(config)

    assert token_path.read_text() == '{"token": "novo"}'


def test_refreshed_token_is_not_written_back_to_a_foreign_file(tmp_path, monkeypatch):
    """The token may be shared with another project that owns and refreshes
    it. Writing google-auth's serialisation over it rewrites its shape (a
    `scopes` list where the owner keeps a `scope` string, plus expiry and
    universe_domain) and can break the owner. Refresh in memory instead.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "home"))
    foreign = tmp_path / "outro-projeto" / "token.json"
    foreign.parent.mkdir(parents=True)
    original = '{"account": "x", "scope": "a b", "refresh_token": "r"}'
    foreign.write_text(original)

    mock_credentials = MagicMock(valid=False, expired=True, refresh_token="r")
    mock_credentials.to_json.return_value = '{"token": "sobrescrito"}'
    config = {"email": {"token_path": str(foreign)}}

    with (
        patch("moonlighter.tracking.gmail_client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail_client.build"),
        patch("moonlighter.tracking.gmail_client.Request"),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        setup_gmail_service(config)

    mock_credentials.refresh.assert_called_once()
    assert foreign.read_text() == original, "arquivo de outro projeto foi alterado"


def test_raises_gmail_auth_error_when_token_missing(tmp_path):
    config = {
        "email": {
            "credentials_path": str(tmp_path / "gmail-client.json"),
            "token_path": str(tmp_path / "nonexistent-token.json"),
        }
    }

    with pytest.raises(GmailAuthError, match="setup_email"):
        setup_gmail_service(config)


def test_refreshes_expired_token(tmp_path, monkeypatch):
    # Persistence now only happens for a token file we own, so the fixture
    # has to put it inside MOONLIGHTER_HOME.
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    token_path = str(tmp_path / "gmail-token.json")
    config = {
        "email": {
            "credentials_path": str(tmp_path / "creds.json"),
            "token_path": token_path,
        }
    }

    Path(token_path).write_text("{}")  # token precisa existir

    mock_credentials = MagicMock()
    mock_credentials.valid = False
    mock_credentials.expired = True
    mock_credentials.refresh_token = "some-refresh-token"
    mock_credentials.to_json.return_value = '{"token": "refreshed"}'

    with (
        patch("moonlighter.tracking.gmail_client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail_client.Request"),
        patch("moonlighter.tracking.gmail_client.build") as mock_build,
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()

        setup_gmail_service(config)

    mock_credentials.refresh.assert_called_once()
    assert Path(token_path).read_text() == '{"token": "refreshed"}'


def test_setup_gmail_service_raises_without_google_libs():
    """Credentials None (libs missing) → GmailAuthError (gmail_client.setup_gmail_service)."""
    with (
        patch("moonlighter.tracking.gmail_client.Credentials", None),
        pytest.raises(GmailAuthError, match="google-api-python-client"),
    ):
        setup_gmail_service({"email": {}})


def test_setup_gmail_service_without_email_block_raises_config_message():
    with pytest.raises(GmailAuthError, match=r"email.token_path is not configured"):
        setup_gmail_service({})
