"""The wrapper every MCP tool goes through: timing, logging and one uniform failure line."""

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

from moonlighter.core.log import get_logger

logger = get_logger(__name__)


def tool_logged(tool: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Wrap an MCP tool coroutine to log start, end and elapsed time.

    Any *unexpected* exception becomes a uniform client-facing line, and the full
    traceback goes to the log.

    Expected domain errors (a tool returning a friendly 'not found' string) never reach
    the catch — the tool returns first. Only a raised exception is caught here.
    """
    name = tool.__name__

    @functools.wraps(tool)
    async def wrapper(*positional_arguments: Any, **keyword_arguments: Any) -> str:
        logger.info("tool=%s start", name)
        started_at = time.monotonic()
        try:
            return await tool(*positional_arguments, **keyword_arguments)
        except Exception as error:
            logger.exception("tool=%s failed", name)
            return f"⚠️ tool '{name}' failed: {error}"
        finally:
            logger.info("tool=%s end elapsed=%.1fs", name, time.monotonic() - started_at)

    return wrapper
