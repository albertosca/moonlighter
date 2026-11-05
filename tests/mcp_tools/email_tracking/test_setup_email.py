"""setup_email resolves the credentials path and turns each OAuth failure into a message."""

from unittest.mock import MagicMock, patch

from moonlighter.mcp_tools.email_tracking import setup_email
from moonlighter.tracking.gmail_client import GmailAuthError

from tests._context import make_test_context


async def test_setup_email_calls_gmail_flow():
    """setup_email should start the OAuth flow and confirm success."""

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
        }
    }
    with (
        patch("moonlighter.mcp_tools.email_tracking.setup_gmail_service") as mock_setup,
        patch("moonlighter.mcp_tools.email_tracking.run_gmail_oauth") as mock_oauth,
        patch("os.path.exists", return_value=True),
    ):
        mock_oauth.return_value = None
        mock_setup.return_value = MagicMock()
        result = await setup_email(context=make_test_context(config=test_config))

    assert "success" in result.lower() or "configured" in result.lower()


async def test_setup_email_raises_friendly_error_when_client_json_missing():
    """setup_email should return a clear message if gmail-client.json does not exist."""

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "/nonexistent/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
        }
    }
    result = await setup_email(context=make_test_context(config=test_config))

    assert "client" in result.lower() or "credential" in result.lower() or "error" in result.lower()


async def test_setup_email_resolves_a_relative_credentials_path_under_moonlighter_home(
    tmp_path, monkeypatch
):
    """IMPORTANT 6: DEFAULTS ships relative filenames ("gmail-client.json"), and
    setup_email must resolve them under MOONLIGHTER_HOME -- not hardcode
    ~/.moonlighter, which ignores a MOONLIGHTER_HOME override."""

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    (tmp_path / "gmail-client.json").write_text("{}")
    test_config = {
        "email": {"credentials_path": "gmail-client.json", "token_path": "gmail-token.json"}
    }
    with (
        patch("moonlighter.mcp_tools.email_tracking.setup_gmail_service") as mock_setup,
        patch("moonlighter.mcp_tools.email_tracking.run_gmail_oauth") as mock_oauth,
    ):
        mock_oauth.return_value = None
        mock_setup.return_value = MagicMock()
        result = await setup_email(context=make_test_context(config=test_config))

    assert "success" in result.lower() or "configured" in result.lower()
    called_creds_path, called_token_path = mock_oauth.call_args.args[:2]
    assert called_creds_path == str(tmp_path / "gmail-client.json")
    assert called_token_path == str(tmp_path / "gmail-token.json")


async def test_setup_email_leaves_an_absolute_credentials_path_untouched(tmp_path, monkeypatch):
    """A user who already points credentials_path at their own absolute location
    must not have it silently rewritten to somewhere under MOONLIGHTER_HOME."""

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path / "not-this-one"))
    creds = tmp_path / "somewhere-else" / "client.json"
    creds.parent.mkdir()
    creds.write_text("{}")
    test_config = {
        "email": {"credentials_path": str(creds), "token_path": str(tmp_path / "t.json")}
    }
    with (
        patch("moonlighter.mcp_tools.email_tracking.setup_gmail_service") as mock_setup,
        patch("moonlighter.mcp_tools.email_tracking.run_gmail_oauth") as mock_oauth,
    ):
        mock_oauth.return_value = None
        mock_setup.return_value = MagicMock()
        result = await setup_email(context=make_test_context(config=test_config))

    assert "success" in result.lower() or "configured" in result.lower()
    called_creds_path = mock_oauth.call_args.args[0]
    assert called_creds_path == str(creds)


async def test_setup_email_missing_credentials_path_gives_a_clear_message():
    """MINOR 8: Path("").expanduser() is ".", a directory that always exists --
    without this guard the tool falls through to a confusing 'Is a directory'
    failure deep in the OAuth flow instead of naming the actual problem."""

    test_config = {"email": {"token_path": "gmail-token.json"}}
    result = await setup_email(context=make_test_context(config=test_config))
    assert "credentials_path" in result
    assert "not configured" in result.lower()


async def test_setup_email_handles_auth_error(tmp_path):
    """GmailAuthError during OAuth → friendly message (mcp_tools.email_tracking.setup_email)."""

    creds = tmp_path / "gmail-client.json"
    creds.write_text("{}")
    test_config = {
        "email": {"credentials_path": str(creds), "token_path": str(tmp_path / "t.json")}
    }
    with patch(
        "moonlighter.mcp_tools.email_tracking.run_gmail_oauth",
        side_effect=GmailAuthError("invalid token"),
    ):
        result = await setup_email(context=make_test_context(config=test_config))
    assert "Gmail" in result
    assert "invalid token" in result


async def test_setup_email_handles_unexpected_error(tmp_path):
    """Unexpected exception during OAuth → unexpected-error message (mcp_tools.email_tracking.setup_email)."""

    creds = tmp_path / "gmail-client.json"
    creds.write_text("{}")
    test_config = {
        "email": {"credentials_path": str(creds), "token_path": str(tmp_path / "t.json")}
    }
    with patch(
        "moonlighter.mcp_tools.email_tracking.run_gmail_oauth", side_effect=RuntimeError("boom")
    ):
        result = await setup_email(context=make_test_context(config=test_config))
    assert "unexpected" in result.lower()
