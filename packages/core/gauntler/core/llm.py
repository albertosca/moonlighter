import asyncio
import os
from pathlib import Path
from typing import Any, Protocol

import anthropic
from anthropic.types import TextBlock
from gauntler.core.config import gauntler_home


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


# Postura de sandbox validada empiricamente (canário, 2026-07-09 —
# specs/2026-07-09-s2-canary-experiment-results.md): sem isso, o `-p` default lê
# qualquer arquivo do disco sem prompt de permissão, enxerga 168 tools MCP da
# conta e injeta o CLAUDE.md global do Alberto em toda avaliação de vaga.
# --bare NUNCA entra aqui: desliga OAuth/keychain, que é a autenticação de
# assinatura que o backend 'cli' inteiro existe para usar.
_CLI_SANDBOX_ARGS: tuple[str, ...] = (
    "--safe-mode",
    "--no-session-persistence",
    "--tools",
    "",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
)


def _cli_workdir() -> Path:
    """cwd dedicado e neutro para o subprocesso do CLI — nunca o repositório
    (S-02): um cwd sem valor nenhum para um agente comprometido explorar."""
    workdir = gauntler_home() / "cli-workdir"
    workdir.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    return workdir


async def _call_cli(prompt: str, model: str, cache_prefix: str | None = None) -> str:
    """Call Claude via the installed `claude` CLI subprocess, sandboxed.

    Uses the active Claude Code session — no API key needed.
    The `model` parameter is ignored (CLI uses whichever model the session provides).
    O cache_prefix é concatenado antes do prompt (o CLI não expõe cache_control);
    o efeito de cache real só existe no backend api.

    O prompt vai por STDIN, nunca por argv (S-01): remove a exposição em `ps` e
    torna a injeção de argumento estrutturalmente impossível (não há prompt em
    argv para virar flag). O subprocesso roda com um conjunto explícito de
    flags de bloqueio (S-02/S-14/S-15) e num cwd neutro fora do repositório.
    """
    full = f"{cache_prefix}\n\n{prompt}" if cache_prefix is not None else prompt
    # Strip ANTHROPIC_API_KEY so the CLI uses the claude.ai session (subscription)
    # instead of the API key (which requires separate API credits).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = await asyncio.create_subprocess_exec(
        "claude",
        *_CLI_SANDBOX_ARGS,
        "-p",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(_cli_workdir()),
    )
    stdout, stderr = await proc.communicate(input=full.encode())
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
