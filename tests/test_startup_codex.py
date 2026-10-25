from moonlighter.startup import validate_startup


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
