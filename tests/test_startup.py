from unittest.mock import patch

import pytest
from moonlighter.startup import StartupWarning, validate_startup


@pytest.fixture(autouse=True)
def _fake_claude_on_path():
    """`claude` is installed on the dev machine and never in CI. Without a fixed
    resolution the cli-backend check would make this module pass locally and
    fail in CI. Tests that need it absent patch `which` themselves."""
    with patch("moonlighter.startup.shutil.which", return_value="/usr/local/bin/claude"):
        yield


# ── profile ───────────────────────────────────────────────────────────────────


def test_validate_startup_empty_profile_produces_warn():
    warnings = validate_startup(config={}, profile={})
    assert any(
        warning.level == "warn" and "profile" in warning.message.lower() for warning in warnings
    )


def test_validate_startup_non_empty_profile_no_profile_warning():
    warnings = validate_startup(config={}, profile={"skills": [{"name": "Python"}]})
    assert not any("profile" in warning.message.lower() for warning in warnings)


# ── criteria.location_precedence ──────────────────────────────────────────────


@pytest.mark.parametrize("value", ["Generic", "specfic", "global"])
def test_an_unknown_location_precedence_warns_and_names_the_valid_values(value):
    """A typo silently meant "specific" (2026-09-29 review): say so at startup."""
    profile = {"criteria": {"location_precedence": value}}
    warnings = validate_startup(config={}, profile=profile)
    messages = [warning.message for warning in warnings if "location_precedence" in warning.message]
    assert len(messages) == 1
    assert value in messages[0] and "specific" in messages[0] and "generic" in messages[0]


@pytest.mark.parametrize(
    "profile", [{"criteria": {"location_precedence": "generic"}}, {"criteria": {}}, {"skills": []}]
)
def test_a_valid_or_absent_location_precedence_is_quiet(profile):
    warnings = validate_startup(config={}, profile=profile)
    assert not any("location_precedence" in warning.message for warning in warnings)


# ── ANTHROPIC_API_KEY ─────────────────────────────────────────────────────────


def test_validate_startup_cli_backend_without_the_claude_binary_produces_error(monkeypatch):
    """The symmetric hole to the API-key check: the api path was guarded and the
    cli path was not, so a user who picked 'cli' without Claude Code installed
    learned about it mid-scan, once per job, instead of at startup."""
    monkeypatch.setattr("moonlighter.startup.shutil.which", lambda _: None)
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert any(
        warning.level == "error" and "claude" in warning.message.lower() for warning in warnings
    )


def test_validate_startup_cli_backend_with_the_claude_binary_is_quiet(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.shutil.which", lambda _: "/usr/local/bin/claude")
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert not any("claude" in warning.message.lower() for warning in warnings)


def test_validate_startup_omitted_backend_does_not_demand_an_api_key(monkeypatch):
    """An omitted llm_backend now means 'cli', so the API-key error must not
    fire -- otherwise the default and the check disagree about the same key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("moonlighter.startup.shutil.which", lambda _: "/usr/local/bin/claude")
    warnings = validate_startup(config={}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


def test_validate_startup_missing_api_key_produces_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={"llm_backend": "api"}, profile={"skills": []})
    assert any(
        warning.level == "error" and "ANTHROPIC_API_KEY" in warning.message for warning in warnings
    )


def test_validate_startup_api_key_present_no_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    warnings = validate_startup(config={"llm_backend": "api"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


def test_validate_startup_cli_backend_skips_api_key_error(monkeypatch):
    """BUG-05: with llm_backend='cli' no API key is used, so its absence
    must not raise an error."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


def test_validate_startup_cursor_backend_without_the_cli_produces_error(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: None)
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    errors = [w for w in warnings if w.level == "error"]
    assert len(errors) == 1
    assert "agent login" in errors[0].message
    assert "claude" not in errors[0].message.lower()


def test_validate_startup_cursor_backend_with_agent_is_quiet(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/agent")
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any(w.level == "error" for w in warnings)


def test_validate_startup_cursor_backend_accepts_cursor_agent_fallback(monkeypatch):
    monkeypatch.setattr(
        "moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/cursor-agent"
    )
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any(w.level == "error" for w in warnings)


def test_validate_startup_cursor_backend_does_not_demand_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/agent")
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in w.message for w in warnings)


# ── cv.pdf ────────────────────────────────────────────────────────────────────


def test_validate_startup_missing_cv_produces_warn(tmp_path):
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(tmp_path / "nonexistent.pdf"),
    )
    assert any(warning.level == "warn" and "cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_default_cv_path_resolves_under_moonlighter_home(monkeypatch, tmp_path):
    """When cv_path is omitted, the default is <MOONLIGHTER_HOME>/cv.pdf, not a path
    relative to the installed package (which is an ephemeral cache dir under uvx)."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    warnings = validate_startup(config={}, profile={"skills": []})
    cv_warning = next(warning for warning in warnings if "cv" in warning.message.lower())
    assert str(tmp_path / "cv.pdf") in cv_warning.message


def test_validate_startup_honours_a_configured_cv_default(tmp_path):
    """A user who points cv.default somewhere else must not be told their CV is
    missing -- the composer resolves the CV through config, so the warning must too."""
    cv = tmp_path / "resumes" / "senior.pdf"
    cv.parent.mkdir()
    cv.touch()
    warnings = validate_startup(
        config={"cv": {"default": str(cv)}},
        profile={"skills": []},
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_names_the_configured_cv_when_it_is_missing(tmp_path):
    """And when it really is missing, the warning names the configured path --
    not MOONLIGHTER_HOME/cv.pdf, which the applier would never have looked at."""
    configured = tmp_path / "resumes" / "senior.pdf"
    warnings = validate_startup(
        config={"cv": {"default": str(configured)}},
        profile={"skills": []},
    )
    cv_warning = next(warning for warning in warnings if "cv" in warning.message.lower())
    assert str(configured) in cv_warning.message


def test_validate_startup_resolves_a_relative_cv_default_from_moonlighter_home(
    monkeypatch, tmp_path
):
    """Relative cv.default resolves from MOONLIGHTER_HOME, matching resolve_cv_path."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    cv = tmp_path / "my-cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={"cv": {"default": "my-cv.pdf"}},
        profile={"skills": []},
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


def test_validate_startup_cv_present_no_cv_warning(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={},
        profile={"skills": []},
        cv_path=str(cv),
    )
    assert not any("cv" in warning.message.lower() for warning in warnings)


# ── browser path ──────────────────────────────────────────────────────────────


def test_validate_startup_missing_browser_produces_warn():
    warnings = validate_startup(
        config={"browser_path": "/nonexistent/Chrome"},
        profile={"skills": []},
    )
    assert any(
        warning.level == "warn" and "browser" in warning.message.lower() for warning in warnings
    )


def test_validate_startup_legacy_brave_path_still_works(tmp_path):
    """Backwards compat: the legacy brave_path key is still recognized (via browser_executable)."""
    brave = tmp_path / "brave"
    brave.touch()
    warnings = validate_startup(
        config={"brave_path": str(brave)},
        profile={"skills": []},
    )
    assert not any("browser" in warning.message.lower() for warning in warnings)


# ── all clear ─────────────────────────────────────────────────────────────────


def test_validate_startup_all_ok_returns_no_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    browser = tmp_path / "chrome"
    browser.touch()
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={"browser_path": str(browser)},
        profile={"skills": [{"name": "Python"}]},
        cv_path=str(cv),
    )
    assert not any(warning.level == "error" for warning in warnings)


# ── return type ───────────────────────────────────────────────────────────────


def test_validate_startup_returns_list_of_startup_warnings():
    result = validate_startup(config={}, profile={})
    assert isinstance(result, list)
    assert all(isinstance(warning, StartupWarning) for warning in result)
