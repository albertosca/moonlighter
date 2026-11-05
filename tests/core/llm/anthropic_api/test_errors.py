from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from moonlighter.core.llm.anthropic_api import make_api_caller


async def test_make_api_caller_propagates_exception():
    """Exceptions from the API are not swallowed."""
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("rate limit"))

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        with pytest.raises(Exception, match="rate limit"):
            await caller("prompt", "model")


async def test_make_api_caller_raises_on_non_text_block():
    """content[0] is not a TextBlock → RuntimeError (moonlighter.core.llm.anthropic_api)."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock()]  # no spec=TextBlock → isinstance False
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client
    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        with pytest.raises(RuntimeError, match="non-text block"):
            await caller("prompt", "model")


async def test_make_api_caller_non_text_block_message_is_pinned_word_for_word():
    message = MagicMock()
    message.content = [MagicMock()]
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=message)
    fake_anthropic = MagicMock()
    fake_anthropic.AsyncAnthropic.return_value = client
    with patch("moonlighter.core.llm.anthropic_api.anthropic", fake_anthropic):
        caller = make_api_caller()
        with pytest.raises(RuntimeError) as raised:
            await caller("prompt", "model")
    assert str(raised.value) == "unexpected model response (non-text block)"
