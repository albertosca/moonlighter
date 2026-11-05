"""Whichever LLM backend is configured needs its own credential, reported once at startup."""

import pytest

from moonlighter.core.config.backends import LLM_BACKENDS
from moonlighter.startup import validate_startup


def test_validate_startup_cli_backend_without_the_claude_binary_produces_error(monkeypatch):
    """The symmetric hole to the API-key check: the api path was guarded and the
    cli path was not, so a user who picked 'cli' without Claude Code installed
    learned about it mid-scan, once per job, instead of at startup.
    """
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
    fire -- otherwise the default and the check disagree about the same key.
    """
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
    must not raise an error.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


def test_validate_startup_cursor_backend_without_the_cli_produces_error(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: None)
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    errors = [warning for warning in warnings if warning.level == "error"]
    assert len(errors) == 1
    assert "agent login" in errors[0].message
    assert "claude" not in errors[0].message.lower()


def test_validate_startup_cursor_backend_with_agent_is_quiet(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/agent")
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any(warning.level == "error" for warning in warnings)


def test_validate_startup_cursor_backend_accepts_cursor_agent_fallback(monkeypatch):
    monkeypatch.setattr(
        "moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/cursor-agent"
    )
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any(warning.level == "error" for warning in warnings)


def test_validate_startup_cursor_backend_does_not_demand_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("moonlighter.startup.cursor_executable", lambda: "/usr/local/bin/agent")
    warnings = validate_startup(config={"llm_backend": "cursor"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


def test_codex_backend_without_the_cli_produces_an_error(monkeypatch):
    monkeypatch.setattr("moonlighter.startup.codex_executable", lambda: None)
    warnings = validate_startup(config={"llm_backend": "codex"}, profile={"skills": []})
    errors = [warning for warning in warnings if warning.level == "error"]
    assert len(errors) == 1
    assert "codex login" in errors[0].message
    assert "claude" not in errors[0].message.lower()


def test_codex_backend_with_the_cli_is_quiet_and_asks_for_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("moonlighter.startup.codex_executable", lambda: "/opt/bin/codex")
    warnings = validate_startup(config={"llm_backend": "codex"}, profile={"skills": []})
    assert not any(warning.level == "error" for warning in warnings)
    assert not any("ANTHROPIC_API_KEY" in warning.message for warning in warnings)


@pytest.mark.parametrize("backend", LLM_BACKENDS)
def test_every_llm_backend_has_a_credential_check(backend):
    """A backend added to LLM_BACKENDS without a credential check would raise KeyError at startup."""
    warnings = validate_startup(config={"llm_backend": backend}, profile={"skills": []})
    assert isinstance(warnings, list)
