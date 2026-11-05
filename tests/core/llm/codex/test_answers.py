from unittest.mock import patch

import pytest

from moonlighter.core.llm.codex import call_codex
from tests.core.llm.codex.fake_codex import fake_codex


async def test_the_answer_is_the_last_message_the_cli_wrote():
    create, calls, _ = fake_codex("the answer\n")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        result = await call_codex("my prompt", "gpt-5")
    assert result == "the answer\n"
    assert [call[0][1:3] for call in calls] == [
        ("login", "status"),
        ("--ask-for-approval", "never"),
    ]


async def test_the_prompt_goes_over_stdin_and_never_argv():
    create, calls, processes = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("SECRET-PROMPT", "gpt-5")
    exec_argv, exec_options = calls[1]
    assert all("SECRET-PROMPT" not in argument for argument in exec_argv)
    assert exec_argv[-1] == "-"
    assert processes[1].communicate.call_args.kwargs["input"] == b"SECRET-PROMPT"
    assert exec_options["start_new_session"] is True


async def test_cache_prefix_is_concatenated_before_the_prompt():
    create, _, processes = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("DYNAMIC", "gpt-5", cache_prefix="STATIC")
    assert processes[1].communicate.call_args.kwargs["input"] == b"STATIC\n\nDYNAMIC"


async def test_the_model_is_forwarded():
    create, calls, _ = fake_codex("ok")
    with patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create):
        await call_codex("prompt", "gpt-5")
    exec_argv = calls[1][0]
    assert exec_argv[exec_argv.index("--model") + 1] == "gpt-5"


@pytest.mark.parametrize("answer", [None, "", "   \n"])
async def test_no_answer_is_an_error_not_an_empty_string(answer):
    create, _, _ = fake_codex(answer)
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError, match=r"no final response|empty"),
    ):
        await call_codex("prompt", "gpt-5")


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (None, "codex CLI wrote no final response"),
        ("", "codex CLI returned an empty final response"),
        ("   \n", "codex CLI returned an empty final response"),
    ],
)
async def test_a_missing_answer_message_is_pinned_word_for_word(answer, message):
    create, _, _ = fake_codex(answer)
    with (
        patch("moonlighter.core.llm.codex.asyncio.create_subprocess_exec", create),
        pytest.raises(RuntimeError) as raised,
    ):
        await call_codex("prompt", "gpt-5")
    assert str(raised.value) == message
