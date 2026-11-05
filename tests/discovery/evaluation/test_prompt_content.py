"""Tests for the text of the single-job prompt and the rules both prefixes carry."""

from moonlighter.discovery.evaluation.engagement import engagement_section
from moonlighter.discovery.evaluation.prompts import EVAL_BATCH_PREFIX, EVAL_PREFIX
from moonlighter.discovery.evaluation.single import evaluate_job

from tests.discovery.evaluation.evaluation_fakes import (
    JOB_DESCRIPTION,
    MOCK_LLM_RESPONSE,
    PROFILE,
    evaluate_once,
    recording_caller,
)


async def test_evaluate_job_prompt_carries_location_and_remote_type():
    # The 32/32 gitlab false positives happened because the LLM judged
    # eligibility without ever seeing the structured location field.
    seen = {}

    async def spy(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        seen["prompt"] = prompt
        seen["prefix"] = cache_prefix
        return MOCK_LLM_RESPONSE

    await evaluate_job(
        company="Acme",
        title="Eng",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _caller=spy,
        location="Bangalore, India",
        remote_type="remote",
    )
    assert "Location: Bangalore, India" in seen["prompt"]
    assert "Remote type: remote" in seen["prompt"]
    assert "Regional eligibility" in seen["prefix"]


async def test_eval_prefixes_carry_the_mandatory_requirement_rule():
    # Live 2026-08-21 (gympass #3404 vs #3416): a posting mandating
    # Kotlin/Go/Java (none in the profile) outscored its twin mandating Python
    # (8y in the profile) — the evaluator saw the requirement and explained it
    # away as "inconsistent with the rest of the description". The rule must
    # be in BOTH prompt prefixes, must forbid that rationalization, must
    # require an "unmet mandatory:" caveat, and must NOT be a hard filter
    # (an Elixir-mandatory posting is attractive, never eliminated).
    for prefix in (EVAL_PREFIX, EVAL_BATCH_PREFIX):
        assert "## Mandatory requirements" in prefix
        assert "unmet mandatory:" in prefix
        assert "inconsistent" in prefix  # the named forbidden rationalization
        assert "NOT a hard filter" in prefix


async def test_eval_prefixes_carry_the_engagement_type_rule():
    # Alberto, 2026-08-24: contract/freelance/fixed-term postings (make #3264
    # freelance ago-dez/2026, Flywheel "Contract" in the title) competed at the
    # same score as permanent roles. He still wants them in the queue, just
    # lower — a discount, never a cut, same philosophy as the stale-Elixir
    # discount and the unmet-mandatory rule.
    # The rule is now the profile's (preferences.engagement), no longer baked in.
    section = engagement_section({"preferences": {"engagement": "permanent full-time"}})
    assert "targets permanent full-time positions" in section
    assert "contract-based:" in section
    assert "NOT a hard filter" in section
    for prefix in (EVAL_PREFIX, EVAL_BATCH_PREFIX):
        assert "{engagement_section}" in prefix


async def test_evaluate_job_omits_location_lines_when_absent():
    seen = {}

    async def spy(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        seen["prompt"] = prompt
        return MOCK_LLM_RESPONSE

    await evaluate_job(
        company="Acme",
        title="Eng",
        description=JOB_DESCRIPTION,
        profile=PROFILE,
        model="claude-sonnet-4-6",
        _caller=spy,
        location=None,
        remote_type=None,
    )
    assert "Location:" not in seen["prompt"]
    assert "Remote type:" not in seen["prompt"]


async def test_the_single_posting_body_is_company_title_location_remote_type_description():
    caller, calls = recording_caller(MOCK_LLM_RESPONSE)
    await evaluate_once(caller, location="Bangalore, India", remote_type="remote")
    assert (
        "Company: Co\nTitle: Eng\nLocation: Bangalore, India\nRemote type: remote\nDescription:\ndesc"
        in calls[0][0]
    )


async def test_empty_location_and_remote_type_add_no_lines():
    caller, calls = recording_caller(MOCK_LLM_RESPONSE)
    await evaluate_once(caller, location="", remote_type="")
    assert "Company: Co\nTitle: Eng\nDescription:\ndesc" in calls[0][0]
