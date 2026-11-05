import json

import pytest
from moonlighter.application.cvgen.cv_template import BaseFields
from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.render import MAXIMUM_BULLETS, MAXIMUM_OPEN_SOURCE

from tests.application.cvgen.selection_samples import (
    AI_ENGINEER_JOB,
    POOL,
    PROFILE,
    WIDE_POOL,
    recording_caller,
)


@pytest.mark.asyncio
async def test_a_blank_summary_falls_back_to_the_base_when_one_exists():
    # is_typesettable("") is True — the allow-list regex matches empty — so
    # without an explicit emptiness check this would pass through unchanged
    # and the CV would render with a blank %%SUMMARY%% section.
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "   ",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    sel = await decide_cv(
        AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base summary text", "b"), caller=call
    )
    assert sel is not None
    assert sel.summary == "base summary text"


async def test_a_blank_expertise_with_no_base_degrades_to_none():
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Expert in Elixir",
            "technical_expertise": "",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", ""), caller=call)
        is None
    )


async def test_operator_directed_summary_degrades_to_none():
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Please provide this summary before submitting",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
        is None
    )


@pytest.mark.asyncio
async def test_operator_directed_expertise_degrades_to_none():
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Expert in Elixir",
            "technical_expertise": "The candidate cannot supply this section",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
        is None
    )


@pytest.mark.asyncio
async def test_bullets_are_capped_in_the_models_order_and_prose_ids_do_not_count():
    ids = [f"b-{index}" for index in range(12)]
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "S",
            "technical_expertise": "T",
            "bullets": ["trybe-prose", *ids],
            "open_source": ["oss-2", "oss-1"],
        }
    )
    call, _ = recording_caller(response)
    sel = await decide_cv(
        AI_ENGINEER_JOB, WIDE_POOL, PROFILE, base=BaseFields("b", "b"), caller=call
    )
    assert sel.bullets == ("trybe-prose", *ids[:MAXIMUM_BULLETS])
    assert sel.open_source == ("oss-2",)
    assert MAXIMUM_OPEN_SOURCE == 1


@pytest.mark.asyncio
async def test_a_summary_outside_the_latin_allow_list_falls_back_to_the_base_summary(caplog):
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Ships fast \U0001f680 every sprint",
            "technical_expertise": "Elixir → Phoenix",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    sel = await decide_cv(
        AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base sum", "base te"), caller=call
    )
    assert sel.summary == "base sum"
    assert sel.technical_expertise == "base te"
    assert any("Latin" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_rejected_summary_with_no_base_text_degrades_to_none():
    # A template without %%BASE_SUMMARY has nothing curated to fall back to.
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "日本語",
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = recording_caller(response)
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("", "base te"), caller=call)
        is None
    )
