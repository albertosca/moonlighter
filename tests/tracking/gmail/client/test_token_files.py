"""Reading the scopes a token file declares, and whether the token file is ours."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from moonlighter.tracking.gmail import client as gmail_client
from moonlighter.tracking.gmail.client import _token_scopes, setup_gmail_service


class TestTokenScopes:
    def test_reads_the_scope_string_format(self, tmp_path):
        """The token may be maintained by another project that writes google's
        wire format: a single space-separated `scope` string, not a `scopes` list.
        """
        token_file = tmp_path / "t.json"
        token_file.write_text('{"scope": "https://a/gmail.modify https://a/calendar"}')
        assert _token_scopes(token_file) == ["https://a/gmail.modify", "https://a/calendar"]

    def test_reads_the_scopes_list_format(self, tmp_path):
        token_file = tmp_path / "t.json"
        token_file.write_text('{"scopes": ["https://a/gmail.readonly"]}')
        assert _token_scopes(token_file) == ["https://a/gmail.readonly"]

    def test_returns_none_when_the_file_declares_nothing(self, tmp_path):
        token_file = tmp_path / "t.json"
        token_file.write_text('{"refresh_token": "r"}')
        assert _token_scopes(token_file) is None

    def test_returns_none_on_unreadable_json(self, tmp_path):
        token_file = tmp_path / "t.json"
        token_file.write_text("nao e json")
        assert _token_scopes(token_file) is None

    def test_setup_requests_the_granted_scopes_not_the_narrower_one(self, tmp_path, monkeypatch):
        """Refreshing with a scope the grant does not literally contain fails with
        invalid_scope: gmail.modify does not include the string gmail.readonly.
        The token's own scopes are what must be sent; breadth is only warned about.
        """
        monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
        token = tmp_path / "gmail-token.json"
        token.write_text('{"scope": "https://www.googleapis.com/auth/gmail.modify"}')
        config = {"email": {"token_path": str(token)}}

        with (
            patch("moonlighter.tracking.gmail.client.Credentials") as credentials_class,
            patch("moonlighter.tracking.gmail.client.build"),
        ):
            credentials_class.from_authorized_user_file.return_value = MagicMock(
                valid=True, expired=False
            )
            setup_gmail_service(config)

        scopes = credentials_class.from_authorized_user_file.call_args.args[1]
        assert scopes == ["https://www.googleapis.com/auth/gmail.modify"]


class TestIsOurs:
    def test_unresolvable_path_is_not_ours(self, monkeypatch):
        """A path that cannot be resolved must never be treated as ours — the
        consequence of guessing wrong is overwriting another project's token.
        """
        monkeypatch.setattr(
            gmail_client, "moonlighter_home", MagicMock(side_effect=OSError("no home"))
        )
        assert gmail_client._is_ours(Path("/tmp/qualquer/token.json")) is False
