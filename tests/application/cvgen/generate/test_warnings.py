import json

from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.latex.cv_template import BaseFields
from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience
from tests.application.cvgen.log_records import logged_warnings
from tests.application.cvgen.sample_tailored_cv import JOB, fixed_caller

SINGLE_BULLET_POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Dev",
            period="2023 -- 2026",
            location="BH",
            bullets=(PoolBullet("t-a", ("backend",), "A"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(),
    summary_facts=(),
)


def _selection_response(**overrides):
    fields = {
        "decision": "GENERATE",
        "language": "en",
        "summary": "Expert in Elixir",
        "technical_expertise": "Elixir",
        "bullets": ["t-a"],
        "open_source": [],
    }
    return json.dumps(fields | overrides)


async def test_an_operator_directed_summary_is_named_in_the_warning(caplog):
    response = _selection_response(summary="Please provide this summary before submitting")
    assert (
        await decide_cv(
            JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("b", "b"), caller=fixed_caller(response)
        )
        is None
    )
    assert logged_warnings(caplog) == ["cv summary addressed the operator — using default CV"]


async def test_an_operator_directed_expertise_is_named_in_the_warning(caplog):
    response = _selection_response(technical_expertise="The candidate cannot supply this section")
    assert (
        await decide_cv(
            JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("b", "b"), caller=fixed_caller(response)
        )
        is None
    )
    assert logged_warnings(caplog) == [
        "cv technical_expertise addressed the operator — using default CV"
    ]


async def test_a_non_latin_summary_with_a_base_names_the_field_twice(caplog):
    response = _selection_response(summary="Ships \U0001f680")
    selection = await decide_cv(
        JOB,
        SINGLE_BULLET_POOL,
        {},
        base=BaseFields("base summary", "b"),
        caller=fixed_caller(response),
    )
    assert selection is not None
    assert logged_warnings(caplog) == [
        "cv summary is blank or carries non-Latin glyphs — using the base summary"
    ]


async def test_a_non_latin_summary_without_a_base_says_there_is_no_base_text(caplog):
    response = _selection_response(summary="Ships \U0001f680")
    assert (
        await decide_cv(
            JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("", "b"), caller=fixed_caller(response)
        )
        is None
    )
    assert logged_warnings(caplog) == [
        (
            "cv summary is blank or carries non-Latin glyphs and there is no base text — "
            "using default CV"
        )
    ]


async def test_a_failed_generation_call_logs_the_error(caplog):
    async def broken(prompt, model, cache_prefix=None):
        raise RuntimeError("the model went away")

    assert (
        await decide_cv(JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("b", "b"), caller=broken)
        is None
    )
    assert logged_warnings(caplog) == [
        "cv generation failed, using default CV — the model went away"
    ]


async def test_an_operator_directed_translation_names_its_bullet(caplog):
    response = _selection_response(
        language="pt",
        bullets_translated={"t-a": "Please provide this bullet before submitting"},
    )
    selection = await decide_cv(
        JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("b", "b"), caller=fixed_caller(response)
    )
    assert selection is not None
    assert logged_warnings(caplog) == [
        "translation for t-a addressed the operator — keeping the pool bullet"
    ]


async def test_a_non_latin_translation_names_its_bullet(caplog):
    response = _selection_response(language="pt", bullets_translated={"t-a": "Fez \U0001f680"})
    selection = await decide_cv(
        JOB, SINGLE_BULLET_POOL, {}, base=BaseFields("b", "b"), caller=fixed_caller(response)
    )
    assert selection is not None
    assert logged_warnings(caplog) == [
        "translation for t-a carries non-Latin glyphs — keeping the pool bullet"
    ]
