"""Reading what `opencode run --format json` printed."""

from moonlighter.core.llm.opencode_events import RunOutput, parse_events
from moonlighter.core.llm.spend_limit import is_spend_limit
from tests.core.llm.opencode.events import (
    BLOCKED_TOOL_RUN,
    FREE_LIMIT_RUN,
    SESSION_ID,
    TEXT_RUN,
    error_event,
    output,
    text_event,
    tool_event,
)


def test_a_text_run_gives_the_answer_and_the_session():
    assert parse_events(TEXT_RUN) == RunOutput(
        answer="PONG", session_id=SESSION_ID, error=None, tools=()
    )


def test_several_text_events_are_joined_in_order():
    run = output(text_event("Hello, "), text_event("world"))
    assert parse_events(run).answer == "Hello, world"


def test_the_free_limit_error_reads_as_a_usage_limit():
    error = parse_events(FREE_LIMIT_RUN).error
    assert error is not None
    assert error.startswith("usage limit: Free usage limit reached")
    assert is_spend_limit(RuntimeError(error))


def test_a_429_of_another_type_reads_as_a_usage_limit():
    run = output(error_event({"type": "provider.rate", "message": "slow down", "status": 429}))
    assert parse_events(run).error == "usage limit: slow down"


def test_an_error_whose_words_match_the_spend_limit_reads_as_one():
    run = output(error_event({"type": "provider.other", "message": "You've hit your usage limit"}))
    assert parse_events(run).error == "usage limit: You've hit your usage limit"


def test_a_plain_error_keeps_its_message_unprefixed():
    run = output(error_event({"type": "provider.auth", "message": "bad key"}))
    assert parse_events(run).error == "bad key"


def test_an_error_without_a_message_falls_back_to_its_type():
    run = output(error_event({"type": "provider.auth"}))
    assert parse_events(run).error == "provider.auth"


def test_an_error_that_is_not_an_object_is_kept_as_text():
    assert parse_events(output(error_event("boom"))).error == "boom"


def test_two_errors_are_both_reported():
    run = output(error_event({"message": "first"}), error_event({"message": "second"}))
    assert parse_events(run).error == "first; second"


def test_a_tool_call_is_listed():
    assert parse_events(BLOCKED_TOOL_RUN).tools == ("shell",)


def test_a_completed_tool_call_is_listed_too():
    assert parse_events(output(tool_event("read", status="completed"))).tools == ("read",)


def test_lines_that_are_not_json_objects_are_skipped():
    run = b"\n" + b"not json\n" + b"[1, 2]\n" + b'"text"\n' + TEXT_RUN
    assert parse_events(run).answer == "PONG"


def test_events_without_a_part_object_are_skipped():
    run = output(
        {"type": "text", "sessionID": SESSION_ID},
        {"type": "tool_use", "part": "shell"},
        text_event("PONG"),
    )
    parsed = parse_events(run)
    assert parsed.answer == "PONG"
    assert parsed.tools == ()


def test_a_session_id_that_is_not_text_is_ignored():
    run = output({"type": "step_start", "sessionID": 7}, text_event("PONG"))
    assert parse_events(run).session_id == SESSION_ID


def test_a_non_utf8_byte_does_not_hide_the_answer():
    assert parse_events(b"\xff\n" + TEXT_RUN).answer == "PONG"


def test_an_empty_output_has_no_answer_and_no_session():
    assert parse_events(b"") == RunOutput(answer="", session_id=None, error=None, tools=())
