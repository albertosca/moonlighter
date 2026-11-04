from moonlighter.core.config import DEFAULTS


def test_defaults_carry_the_documented_email_paths():
    """credentials_path/token_path must have real defaults so setup_gmail_service
    can name the exact missing key instead of raising a raw KeyError. Relative
    filenames, not ~/.moonlighter/... -- resolve_under_home() resolves them at
    the point of use, honoring a MOONLIGHTER_HOME override (IMPORTANT 6)."""
    assert DEFAULTS["email"]["token_path"] == "gmail-token.json"
    assert DEFAULTS["email"]["credentials_path"] == "gmail-client.json"


def test_the_default_timeout_is_180_seconds():
    assert DEFAULTS["llm_timeout_seconds"] == 180
