import inspect
import logging

from moonlighter._tool_logging import tool_logged


async def test_returns_value_unchanged():
    @tool_logged
    async def sample(first: int, second: int = 2) -> str:
        return f"{first}-{second}"

    assert await sample(1) == "1-2"


async def test_logs_start_and_end(caplog):
    @tool_logged
    async def sample() -> str:
        return "ok"

    with caplog.at_level(logging.INFO):
        await sample()
    text = caplog.text
    assert "tool=sample start" in text
    assert "tool=sample end" in text


async def test_unexpected_exception_returns_uniform_line_and_logs(caplog):
    @tool_logged
    async def sample() -> str:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        result = await sample()
    assert result == "⚠️ tool 'sample' failed: boom"
    assert "boom" in caplog.text  # traceback logged, nothing swallowed silently


def test_preserves_signature():
    @tool_logged
    async def sample(first: int, context: str = "x") -> str:
        return "ok"

    params = list(inspect.signature(sample).parameters)
    assert params == ["first", "context"]  # FastMCP must still see the tool params
