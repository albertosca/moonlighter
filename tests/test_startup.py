import os
import pytest
from candidatador.startup import validate_startup, StartupWarning


# ── profile ───────────────────────────────────────────────────────────────────

def test_validate_startup_empty_profile_produces_warn():
    warnings = validate_startup(config={}, profile={})
    assert any(w.level == "warn" and "profile" in w.message.lower() for w in warnings)


def test_validate_startup_non_empty_profile_no_profile_warning():
    warnings = validate_startup(config={}, profile={"skills": [{"name": "Python"}]})
    assert not any("profile" in w.message.lower() for w in warnings)


# ── ANTHROPIC_API_KEY ─────────────────────────────────────────────────────────

def test_validate_startup_missing_api_key_produces_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={}, profile={"skills": []})
    assert any(w.level == "error" and "ANTHROPIC_API_KEY" in w.message for w in warnings)


def test_validate_startup_api_key_present_no_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    warnings = validate_startup(config={}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in w.message for w in warnings)


def test_validate_startup_cli_backend_skips_api_key_error(monkeypatch):
    """BUG-05: com llm_backend='cli' não se usa API key, então ausência dela
    não deve gerar erro."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    warnings = validate_startup(config={"llm_backend": "cli"}, profile={"skills": []})
    assert not any("ANTHROPIC_API_KEY" in w.message for w in warnings)


# ── cv.pdf ────────────────────────────────────────────────────────────────────

def test_validate_startup_missing_cv_produces_warn(tmp_path):
    warnings = validate_startup(
        config={}, profile={"skills": []},
        cv_path=str(tmp_path / "nonexistent.pdf"),
    )
    assert any(w.level == "warn" and "cv" in w.message.lower() for w in warnings)


def test_validate_startup_cv_present_no_cv_warning(tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={}, profile={"skills": []},
        cv_path=str(cv),
    )
    assert not any("cv" in w.message.lower() for w in warnings)


# ── brave path ────────────────────────────────────────────────────────────────

def test_validate_startup_missing_brave_produces_warn():
    warnings = validate_startup(
        config={"brave_path": "/nonexistent/Brave Browser"},
        profile={"skills": []},
    )
    assert any(w.level == "warn" and "brave" in w.message.lower() for w in warnings)


def test_validate_startup_brave_exists_no_brave_warning(tmp_path):
    brave = tmp_path / "brave"
    brave.touch()
    warnings = validate_startup(
        config={"brave_path": str(brave)},
        profile={"skills": []},
    )
    assert not any("brave" in w.message.lower() for w in warnings)


# ── all clear ─────────────────────────────────────────────────────────────────

def test_validate_startup_all_ok_returns_no_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    brave = tmp_path / "brave"
    brave.touch()
    cv = tmp_path / "cv.pdf"
    cv.touch()
    warnings = validate_startup(
        config={"brave_path": str(brave)},
        profile={"skills": [{"name": "Python"}]},
        cv_path=str(cv),
    )
    assert not any(w.level == "error" for w in warnings)


# ── return type ───────────────────────────────────────────────────────────────

def test_validate_startup_returns_list_of_startup_warnings():
    result = validate_startup(config={}, profile={})
    assert isinstance(result, list)
    assert all(isinstance(w, StartupWarning) for w in result)
