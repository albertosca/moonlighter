"""The scope a config needs, and the warnings when the token's scope differs."""

import logging
from unittest.mock import MagicMock, patch

from moonlighter.tracking.gmail.client import (
    SCOPE_MODIFY,
    SCOPE_READONLY,
    _required_scope,
    _warn_if_scope_mismatch,
    setup_gmail_service,
)
from tests.tracking.archive_settings import archive_config


def test_required_scope_defaults_to_readonly():
    assert _required_scope({}) == SCOPE_READONLY
    assert _required_scope({"email": {"mark_processed": False}}) == SCOPE_READONLY


def test_required_scope_is_modify_when_opted_in():
    assert _required_scope({"email": {"mark_processed": True}}) == SCOPE_MODIFY


def test_setup_gmail_service_warns_on_broader_scope_than_needed(tmp_path, caplog):
    """S-08: a token with gmail.modify when only gmail.readonly is required (the
    default, mark_processed=false) triggers a one-time warning — never
    auto-revoke, just say so plainly.
    """
    token_path = str(tmp_path / "gmail-token.json")
    config = {
        "email": {
            "credentials_path": str(tmp_path / "gmail-client.json"),
            "token_path": token_path,
            "mark_processed": False,
        }
    }

    mock_credentials = MagicMock()
    mock_credentials.valid = True
    mock_credentials.expired = False
    mock_credentials.scopes = ["https://www.googleapis.com/auth/gmail.modify"]

    with (
        patch("moonlighter.tracking.gmail.client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail.client.build") as mock_build,
        patch("os.path.exists", return_value=True),
        caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.client"),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()
        setup_gmail_service(config)

    assert "setup_email" in caplog.text


def test_setup_gmail_service_no_warning_when_scope_already_matches(tmp_path, caplog):
    token_path = str(tmp_path / "gmail-token.json")
    config = {
        "email": {
            "credentials_path": str(tmp_path / "gmail-client.json"),
            "token_path": token_path,
            "mark_processed": False,
        }
    }

    mock_credentials = MagicMock()
    mock_credentials.valid = True
    mock_credentials.expired = False
    mock_credentials.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    with (
        patch("moonlighter.tracking.gmail.client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail.client.build") as mock_build,
        patch("os.path.exists", return_value=True),
        caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.client"),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()
        setup_gmail_service(config)

    assert caplog.text == ""


def test_setup_gmail_service_no_warning_when_scopes_attr_is_a_mock(tmp_path, caplog):
    """Defensive: a mocked/unconfigured .scopes attribute (not a real list) must
    never be iterated — the mismatch check is a no-op in that case.
    """
    token_path = str(tmp_path / "gmail-token.json")
    config = {
        "email": {
            "credentials_path": str(tmp_path / "gmail-client.json"),
            "token_path": token_path,
        }
    }

    mock_credentials = MagicMock()
    mock_credentials.valid = True
    mock_credentials.expired = False
    # .scopes NOT explicitly configured — it's a MagicMock, not a real list

    with (
        patch("moonlighter.tracking.gmail.client.Credentials") as credentials_class,
        patch("moonlighter.tracking.gmail.client.build") as mock_build,
        patch("os.path.exists", return_value=True),
        caplog.at_level(logging.WARNING, logger="moonlighter.tracking.gmail.client"),
    ):
        credentials_class.from_authorized_user_file.return_value = mock_credentials
        mock_build.return_value = MagicMock()
        setup_gmail_service(config)  # must not hang or raise

    assert caplog.text == ""


def test_required_scope_is_modify_when_any_archive_flag_is_on():
    assert _required_scope(archive_config(archive_ref_matched=True)) == SCOPE_MODIFY
    assert _required_scope(archive_config(archive_all_classified=True)) == SCOPE_MODIFY


def test_scope_warning_points_upward_when_modify_is_missing(caplog):
    credentials = MagicMock()
    credentials.scopes = [SCOPE_READONLY]
    with caplog.at_level("WARNING"):
        _warn_if_scope_mismatch(credentials, SCOPE_MODIFY)
    assert any(
        "re-consent" in record.message.lower() or "grant" in record.message.lower()
        for record in caplog.records
    )
