import json

import pytest
from moonlighter.application.cvgen.generate import USE_BASE, decide_cv
from moonlighter.application.cvgen.latex.cv_template import BaseFields
from moonlighter.application.cvgen.latex.render import render_cv

from tests.application.cvgen.selection_samples import (
    AI_ENGINEER_JOB,
    BARE_TEMPLATE,
    GENERATE,
    POOL,
    PROFILE,
    pt_response,
    recording_caller,
)

# --- any shape the model emits degrades; nothing reaches the operator as an
# --- error line instead of the sheet (the module's own contract).
SHAPES = {
    "bullets_translated as a list": ({"bullets_translated": ["\\input{/x}"]}, "translations", {}),
    "bullets_translated as a string": (
        {"bullets_translated": "tudo traduzido"},
        "translations",
        {},
    ),
    "bullets_translated as a number": ({"bullets_translated": 7}, "translations", {}),
    "bullets as an int": ({"bullets": 3}, "bullets", ()),
    "bullets as a string": ({"bullets": "igti-b"}, "bullets", ()),
    "open_source as an int": ({"open_source": 7}, "open_source", ()),
}


@pytest.mark.asyncio
async def test_generate_returns_selection_with_unknown_ids_dropped():
    call, _ = recording_caller(GENERATE)
    sel = await decide_cv(
        AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base sum", "base te"), caller=call
    )
    assert sel is not None
    assert sel.bullets == ("t-b", "t-a")  # ghost-id silently dropped
    assert sel.open_source == ("oss-m",)
    assert sel.summary == "Tailored summary"


@pytest.mark.asyncio
async def test_use_base_returns_sentinel():
    call, _ = recording_caller(json.dumps({"decision": "USE_BASE"}))
    result = await decide_cv(
        AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base sum", "base te"), caller=call
    )
    assert result == USE_BASE  # a genuine model answer, distinct from degradation's None


@pytest.mark.asyncio
async def test_unrecognized_decision_degrades_to_none():
    call, _ = recording_caller(json.dumps({"decision": "MAYBE"}))
    assert (
        await decide_cv(
            AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base sum", "base te"), caller=call
        )
        is None
    )


@pytest.mark.asyncio
async def test_malformed_json_degrades_to_none():
    call, _ = recording_caller("not json at all")
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
        is None
    )


@pytest.mark.asyncio
async def test_valid_json_non_dict_degrades_to_none():
    call, _ = recording_caller(json.dumps(["not", "a", "dict"]))
    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
        is None
    )


@pytest.mark.asyncio
async def test_llm_exception_degrades_to_none():
    async def boom(prompt, model, cache_prefix=None):
        raise RuntimeError("network")

    assert (
        await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=boom)
        is None
    )


@pytest.mark.asyncio
async def test_spend_limit_reraises():
    async def spend_limit_error(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session spend limit")

    with pytest.raises(RuntimeError, match="spend limit"):
        await decide_cv(
            AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=spend_limit_error
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("override", "field", "expected"), SHAPES.values(), ids=list(SHAPES))
async def test_a_wrong_typed_field_degrades_instead_of_raising(override, field, expected):
    # A posting is untrusted input that steers the model's OUTPUT SHAPE, not
    # just its words. decide_cv raising here means prepare_application answers
    # with a traceback line instead of the whole sheet — the operator loses the
    # application, not just the tailored CV.
    response = json.loads(pt_response("Fiz C"))
    response.update(override)
    call, _ = recording_caller(json.dumps(response))
    sel = await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert sel is not None
    assert getattr(sel, field) == expected
    render_cv(BARE_TEMPLATE, sel, POOL)  # and the render still works on it
