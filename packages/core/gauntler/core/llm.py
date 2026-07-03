import asyncio
import os
from typing import Any, Protocol

import anthropic
from anthropic.types import TextBlock


class LLMCaller(Protocol):
    """Protocolo do caller LLM: aceita prompt, model e cache_prefix opcional."""

    async def __call__(
        self, prompt: str, model: str, cache_prefix: str | None = None
    ) -> str: ...

# Sinais de que o LLM esgotou cota/limite de gasto — vale parar o scan e re-tentar
# depois, em vez de tratar como erro da vaga.
SPEND_LIMIT_MARKERS = (
    "spend limit",
    "session limit",
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


async def _call_cli(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    """Call Claude via the installed `claude` CLI subprocess.

    Uses the active Claude Code session — no API key needed.
    The `model` parameter is ignored (CLI uses whichever model the session provides).
    O cache_prefix é concatenado antes do prompt (o CLI não expõe cache_control);
    o efeito de cache real só existe no backend api.
    """
    # Concatena prefix estático + prompt dinâmico quando cache_prefix fornecido.
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    # Strip ANTHROPIC_API_KEY so the CLI uses the claude.ai session (subscription)
    # instead of the API key (which requires separate API credits).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        full,
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

    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        # Quando cache_prefix fornecido, envia dois blocos: o prefixo estático
        # com cache_control ephemeral (marcado para cache no lado do Anthropic)
        # seguido do prompt dinâmico. Sem prefix, envia string simples (retrocompat).
        if cache_prefix is not None:
            content: Any = [
                {"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": prompt},
            ]
        else:
            content = prompt
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        block = message.content[0]
        if not isinstance(block, TextBlock):
            raise RuntimeError("resposta inesperada do modelo (bloco não-texto)")
        return block.text

    return _call
