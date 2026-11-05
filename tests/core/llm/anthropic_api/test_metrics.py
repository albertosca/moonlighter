"""A make_api_caller caller records one call plus the input and output tokens of message.usage
in the active operation_metrics scope, and still counts the call when it fails, with zero
tokens.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock
from moonlighter.core.llm.anthropic_api import make_api_caller
from moonlighter.core.metrics import operation_metrics


async def test_api_caller_records_usage():
    mock_message = MagicMock()
    mock_message.usage = MagicMock(input_tokens=11, output_tokens=22)
    mock_message.content = [MagicMock(spec=TextBlock, text="hello")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        with operation_metrics("op") as metrics:
            out = await caller("hi", "model")

    assert out == "hello"
    assert metrics.calls == 1
    assert metrics.input_tokens == 11
    assert metrics.output_tokens == 22


async def test_api_caller_records_even_on_failure():
    """Time in `finally`: a failed call still counts calls, with 0 tokens
    (usage was never assigned before the exception).
    """
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        with operation_metrics("op") as metrics, contextlib.suppress(RuntimeError):
            await caller("hi", "model")

    assert metrics.calls == 1
    assert metrics.input_tokens == 0
    assert metrics.output_tokens == 0
