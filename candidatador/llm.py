import asyncio
from typing import Callable, Awaitable
import anthropic

# (prompt: str, model: str) -> raw_text: str
LLMCaller = Callable[[str, str], Awaitable[str]]


def make_caller(config: dict) -> LLMCaller:
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
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {stderr.decode()[:300]}"
        )
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
        return message.content[0].text

    return _call
