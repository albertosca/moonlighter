import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic
from anthropic.types import TextBlock

# (prompt: str, model: str) -> raw_text: str
LLMCaller = Callable[[str, str], Awaitable[str]]

# Sinais de que o LLM esgotou cota/limite de gasto — vale parar o scan e re-tentar
# depois, em vez de tratar como erro da vaga.
SPEND_LIMIT_MARKERS = (
    "spend limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)


def is_spend_limit(exc: Exception) -> bool:
    """True se a exceção indica esgotamento de cota/limite de gasto do LLM."""
    msg = str(exc).lower()
    return any(marker in msg for marker in SPEND_LIMIT_MARKERS)


def make_caller(config: dict[str, Any]) -> LLMCaller:
    """Return the appropriate LLM caller based on config['llm_backend'].

    llm_backend: "cli"  → uses the `claude -p` CLI (no API key required)
    llm_backend: "api"  → uses the Anthropic Python SDK (requires ANTHROPIC_API_KEY)
    Default: "api"
    """
    backend = config.get("llm_backend", "api")
    if backend == "cli":
        return _call_cli
    return _make_api_caller()


async def _call_cli(prompt: str, model: str) -> str:
    """Call Claude via the installed `claude` CLI subprocess.

    Uses the active Claude Code session — no API key needed.
    The `model` parameter is ignored (CLI uses whichever model the session provides).
    """
    # Strip ANTHROPIC_API_KEY so the CLI uses the claude.ai session (subscription)
    # instead of the API key (which requires separate API credits).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        prompt,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        detail = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"claude CLI exited with code {proc.returncode}: {detail[:300]}")
    return stdout.decode()


def _make_api_caller(max_tokens: int = 2048) -> LLMCaller:
    """Return an async caller that uses the Anthropic Python SDK.

    Requires ANTHROPIC_API_KEY in the environment.
    """
    client = anthropic.AsyncAnthropic()

    async def _call(prompt: str, model: str) -> str:
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        block = message.content[0]
        if not isinstance(block, TextBlock):
            raise RuntimeError("resposta inesperada do modelo (bloco não-texto)")
        return block.text

    return _call
