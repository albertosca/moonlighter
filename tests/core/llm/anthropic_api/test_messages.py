from unittest.mock import AsyncMock, MagicMock, patch

from anthropic.types import TextBlock
from moonlighter.core.llm.anthropic_api import make_api_caller


async def test_make_api_caller_calls_messages_create():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="api response")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("my prompt", "claude-sonnet-4-6")

    assert result == "api response"
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": "my prompt"}],
    )


async def test_make_api_caller_custom_max_tokens():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller(maximum_tokens=512)
        await caller("prompt", "model")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    assert call_keyword_arguments["max_tokens"] == 512


async def test_make_api_caller_forwards_model():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("prompt", "claude-opus-4-7")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    assert call_keyword_arguments["model"] == "claude-opus-4-7"


async def test_make_api_caller_returns_first_content_text():
    """Returns text of first content block only."""
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(spec=TextBlock, text="first block"),
        MagicMock(spec=TextBlock, text="second block"),
    ]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("prompt", "model")

    assert result == "first block"


def test_make_api_caller_reuses_client_across_calls():
    """make_api_caller() creates ONE AsyncAnthropic instance, not one per call."""
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        make_api_caller()

    assert mock_anthropic.AsyncAnthropic.call_count == 1


async def test_api_caller_satisfies_llm_caller_contract():
    """api caller satisfies (prompt: str, model: str) -> str contract."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="text result")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        result = await caller("hello", "any-model")

    assert isinstance(result, str)


async def test_api_uses_cache_control_block():
    """cache_prefix becomes a content block with cache_control ephemeral in the api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("DYN", "m", cache_prefix="STATIC")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    content = call_keyword_arguments["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "STATIC", "cache_control": {"type": "ephemeral"}}
    assert content[1] == {"type": "text", "text": "DYN"}


async def test_api_no_cache_prefix_sends_plain_string():
    """cache_prefix=None (default) keeps sending a plain string in the api."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(spec=TextBlock, text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic.return_value = mock_client

    with patch("moonlighter.core.llm.anthropic_api.anthropic", mock_anthropic):
        caller = make_api_caller()
        await caller("PROMPT_ONLY", "m")

    call_keyword_arguments = mock_client.messages.create.call_args.kwargs
    content = call_keyword_arguments["messages"][0]["content"]
    assert content == "PROMPT_ONLY"
