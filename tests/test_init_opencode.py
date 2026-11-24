"""The wizard with llm_backend opencode, and the next steps it prints for each client."""

from pathlib import Path

import pytest
import yaml

from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import load_config
from moonlighter.init import next_steps, run_init
from moonlighter.opencode_registration import Registration, registration_snippet

ANSWERS = {"browser_path": "/x", "citizenship_country": "Brazil", "llm_backend": "opencode"}
TARGET = Path("/home/me/.config/opencode/opencode.json")


def test_run_init_writes_opencode_models_that_load_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    path = run_init(tmp_path, {**ANSWERS, "llm_model": "anthropic/claude-sonnet-5-5"})
    written = yaml.safe_load(path.read_text())
    assert written["llm_model"] == "anthropic/claude-sonnet-5-5"
    assert written["eval_model"] == "anthropic/claude-sonnet-5-5"
    assert load_config(path)["llm_backend"] == "opencode"


def test_run_init_keeps_a_separate_opencode_eval_model(tmp_path):
    answers = {
        **ANSWERS,
        "llm_model": "anthropic/claude-sonnet-5-5",
        "eval_model": "anthropic/claude-haiku-5-5",
    }
    path = run_init(tmp_path, answers)
    assert yaml.safe_load(path.read_text())["eval_model"] == "anthropic/claude-haiku-5-5"


@pytest.mark.parametrize("model", ["", "gpt-5", "claude-sonnet-4-6"])
def test_run_init_refuses_opencode_without_a_provider_model(tmp_path, model):
    with pytest.raises(ConfigError, match="provider/model"):
        run_init(tmp_path, {**ANSWERS, "llm_model": model})
    assert not (tmp_path / "config.yaml").exists()


def _text(lines: list[str]) -> str:
    return "\n".join(lines)


def test_a_written_registration_points_at_opencode_mcp_list():
    text = _text(
        next_steps("opencode", Registration(written=True, path=TARGET, reason=f"created {TARGET}"))
    )
    assert str(TARGET) in text
    assert "opencode mcp list" in text
    assert "claude mcp add-json" not in text


def test_a_refused_registration_shows_the_reason_and_the_snippet():
    text = _text(
        next_steps(
            "opencode", Registration(written=False, path=TARGET, reason="it uses the flat form")
        )
    )
    assert "it uses the flat form" in text
    assert f"Add this to {TARGET}:" in text
    assert registration_snippet() in text
    assert "claude mcp add-json" not in text


def test_opencode_without_a_registration_still_gets_the_snippet():
    text = _text(next_steps("opencode", None))
    assert registration_snippet() in text
    assert "claude mcp add-json" not in text


def test_a_claude_backend_keeps_the_claude_line():
    text = _text(next_steps("cli", None))
    assert "claude mcp add-json" in text
    assert "different MCP client" in text


def test_a_claude_backend_that_also_registered_in_opencode_shows_both():
    text = _text(
        next_steps("cli", Registration(written=True, path=TARGET, reason=f"created {TARGET}"))
    )
    assert "claude mcp add-json" in text
    assert "opencode mcp list" in text


@pytest.mark.parametrize(
    ("backend", "registration"),
    [
        ("cli", None),
        ("opencode", None),
        ("opencode", Registration(written=True, path=TARGET, reason="created")),
        ("opencode", Registration(written=False, path=TARGET, reason="reason")),
    ],
)
def test_every_variant_ends_with_get_pipeline_and_never_says_claude(backend, registration):
    lines = next_steps(backend, registration)
    assert (
        lines[-1]
        == "Once connected, ask your agent to run get_pipeline to check your setup for problems."
    )
    assert "ask Claude" not in _text(lines)
