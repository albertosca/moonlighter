"""Tests that each prefix is its template filled with the profile sections."""

import yaml

from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.engagement import engagement_section
from moonlighter.discovery.evaluation.profile_subset import profile_for_eval
from moonlighter.discovery.evaluation.prompts import EVAL_BATCH_PREFIX, EVAL_PREFIX
from moonlighter.discovery.evaluation.regional_eligibility import regional_eligibility_section
from tests.discovery.evaluation.evaluation_fakes import (
    MOCK_LLM_RESPONSE,
    evaluate_once,
    inputs,
    recording_caller,
)

PROFILE_WITH_EVERY_SECTION = {
    "headline": "São Paulo ≤ 2.0 — dev",
    "summary": "s",
    "preferences": {"engagement": "permanent"},
    "criteria": {"location_precedence": "generic"},
}


async def test_the_single_prefix_is_the_template_filled_with_the_three_profile_sections():
    caller, calls = recording_caller(MOCK_LLM_RESPONSE)
    await evaluate_once(caller, profile=PROFILE_WITH_EVERY_SECTION)
    prefix = calls[0][2]
    assert prefix == EVAL_PREFIX.format(
        profile_yaml=yaml.dump(profile_for_eval(PROFILE_WITH_EVERY_SECTION), allow_unicode=True),
        regional_eligibility=regional_eligibility_section(PROFILE_WITH_EVERY_SECTION),
        engagement_section=engagement_section(PROFILE_WITH_EVERY_SECTION),
    )
    assert "headline: São Paulo ≤ 2.0 — dev" in prefix
    assert prefix.index("headline:") < prefix.index("summary:")


async def test_the_batch_prefix_is_the_template_filled_with_the_sections_and_the_job_count():
    caller, calls = recording_caller("[" + ", ".join(['{"score": 1.0}'] * 3) + "]")
    await evaluate_jobs_batch(inputs(3), PROFILE_WITH_EVERY_SECTION, "m", caller=caller)
    prefix = calls[0][2]
    assert prefix == EVAL_BATCH_PREFIX.format(
        profile_yaml=yaml.dump(profile_for_eval(PROFILE_WITH_EVERY_SECTION), allow_unicode=True),
        regional_eligibility=regional_eligibility_section(PROFILE_WITH_EVERY_SECTION),
        engagement_section=engagement_section(PROFILE_WITH_EVERY_SECTION),
        n=3,
    )
    assert "You will be given 3 job postings" in prefix
    assert "exactly 3 objects" in prefix
    assert "headline: São Paulo ≤ 2.0 — dev" in prefix
