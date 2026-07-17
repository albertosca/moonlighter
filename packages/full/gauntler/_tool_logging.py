import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

from gauntler.core.log import get_logger

logger = get_logger(__name__)


def tool_logged(func: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Wrap an MCP tool coroutine: log start/end/elapsed, and turn any *unexpected*
    exception into a uniform client-facing line while logging the full traceback.

    Expected domain errors (a tool returning a friendly 'not found' string) never reach
    the catch — the tool returns first. Only a raised exception is caught here.
    """
    name = func.__name__

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        logger.info("tool=%s start", name)
        t0 = time.monotonic()
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.exception("tool=%s failed", name)
            return f"⚠️ tool '{name}' failed: {exc}"
        finally:
            logger.info("tool=%s end elapsed=%.1fs", name, time.monotonic() - t0)

    return wrapper
