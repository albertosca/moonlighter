"""Backend selection: `make_caller` turns `config['llm_backend']` into an LLM caller."""

from typing import Any

from moonlighter.core.config.backends import llm_backend
from moonlighter.core.config.defaults import DEFAULTS
from moonlighter.core.llm.anthropic_api import make_api_caller
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.claude_cli import call_cli
from moonlighter.core.llm.codex import call_codex
from moonlighter.core.llm.cursor import call_cursor


def make_caller(config: dict[str, Any]) -> LLMCaller:
    """Return the appropriate LLM caller based on config['llm_backend'].

    llm_backend: "cli"     → uses the `claude -p` CLI (no API key required)
    llm_backend: "api"     → uses the Anthropic Python SDK (requires ANTHROPIC_API_KEY)
    llm_backend: "cursor"  → uses the Cursor `agent --print` CLI (`agent login`).
                             Optional config key `cursor_model` is forwarded as
                             `--model`; `llm_model` / `eval_model` are not.
    llm_backend: "codex"   → uses `codex exec` on the user's ChatGPT login
                             (`codex login`). `llm_model` / `eval_model` must name
                             non-Claude models and are forwarded as `--model`.
    Default: "cli". Anything else raises ConfigError rather than silently
    selecting a backend the user did not ask for.
    """
    backend = llm_backend(config)
    if backend == "api":
        return make_api_caller()
    timeout_seconds = config.get("llm_timeout_seconds", DEFAULTS["llm_timeout_seconds"])
    if backend == "cli":
        return _cli_caller(timeout_seconds)
    if backend == "cursor":
        return _cursor_caller(
            str(config.get("cursor_model") or "").strip() or None, timeout_seconds
        )
    return _codex_caller(timeout_seconds)


def _cli_caller(timeout_seconds: float) -> LLMCaller:
    """Bind the shared call timeout to the `claude -p` CLI."""

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return await call_cli(prompt, model, cache_prefix, timeout_seconds=timeout_seconds)

    return _call


def _codex_caller(timeout_seconds: float) -> LLMCaller:
    """Bind the shared call timeout to `codex exec`."""

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return await call_codex(prompt, model, cache_prefix, timeout_seconds=timeout_seconds)

    return _call


def _cursor_caller(cursor_model: str | None, timeout_seconds: float) -> LLMCaller:
    """Bind the optional Cursor model and the shared call timeout.

    The `model` argument stays the Anthropic id the rest of the pipeline passes.
    """

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return await call_cursor(
            prompt,
            model,
            cache_prefix,
            cursor_model=cursor_model,
            timeout_seconds=timeout_seconds,
        )

    return _call
