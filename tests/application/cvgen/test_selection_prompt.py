import json

import pytest
from moonlighter.application.cvgen.cv_template import BaseFields
from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.render import MAXIMUM_BULLETS

from tests.application.cvgen.selection_samples import (
    AI_ENGINEER_JOB,
    POOL,
    PROFILE,
    recording_caller,
)

NURSING_POOL = CVPool(
    experiences=(
        PoolExperience(
            company="General Hospital",
            title="Registered Nurse",
            period="2016 -- 2026",
            location="Lisbon",
            bullets=(PoolBullet("gh-a", ("icu",), "Managed ventilated patients"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(),
    summary_facts=("compute years from career_started",),
)


NURSING_JOB = {"title": "ICU Nurse", "company": "Clinic", "description": "Care for patients."}


async def _prefix_sent(pool):
    seen = {}

    async def caller(prompt, model, cache_prefix=None):
        seen["prefix"] = cache_prefix
        return json.dumps({"decision": "USE_BASE"})

    await decide_cv(
        NURSING_JOB,
        pool,
        {"career_started": 2016},
        base=BaseFields("base summary", "base line"),
        caller=caller,
    )
    return seen["prefix"]


@pytest.mark.asyncio
async def test_prompt_forbids_claims_the_profile_skills_deny():
    """2026-09-24: the tailored summary claimed "production web applications with
    Python" while the profile's skills said no Python in production. The skills
    notes must reach the prompt, and the prompt must treat them as limits."""
    profile = {**PROFILE, "skills": [{"name": "Python", "notes": "studied, never in production"}]}
    call, calls = recording_caller(json.dumps({"decision": "USE_BASE"}))
    await decide_cv(
        AI_ENGINEER_JOB, POOL, profile, base=BaseFields("base sum", "base te"), caller=call
    )
    assert "never in production" in calls["prefix"]
    assert "a claim the profile denies" in calls["prefix"]


@pytest.mark.asyncio
async def test_prompt_carries_pool_ids_base_summary_and_untrusted_posting():
    call, calls = recording_caller(json.dumps({"decision": "USE_BASE"}))
    await decide_cv(
        AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("base sum", "base te"), caller=call
    )
    assert "t-a" in calls["prefix"]
    assert "oss-m" in calls["prefix"]
    assert "base sum" in calls["prefix"]
    assert "USE_BASE" in calls["prefix"]
    assert "never author" in calls["prefix"] or "never write" in calls["prefix"]
    # Translations are asked for as plaintext, not LaTeX: the render escapes
    # them, so a model emitting markup would only produce visible backslashes.
    assert "no LaTeX" in calls["prefix"]
    assert "**bold**" in calls["prefix"]
    assert "Build agents." in calls["prompt"]
    assert "job_posting" in calls["prompt"]  # wrap_untrusted tag


@pytest.mark.asyncio
async def test_prompt_states_the_one_page_budget_and_the_latin_rule():
    call, calls = recording_caller(json.dumps({"decision": "USE_BASE"}))
    await decide_cv(AI_ENGINEER_JOB, POOL, PROFILE, base=BaseFields("b", "b"), caller=call)
    assert "one page" in calls["prefix"]
    assert f"at most {MAXIMUM_BULLETS}" in calls["prefix"]
    assert "no emoji" in calls["prefix"]


async def test_the_prompt_does_not_call_the_expertise_line_technical():
    prefix = await _prefix_sent(NURSING_POOL)
    assert "technical expertise" not in prefix.lower()
    assert "## The base CV's current expertise line" in prefix
    assert "the expertise line" in prefix


async def test_a_pool_without_open_source_has_no_open_source_header():
    prefix = await _prefix_sent(NURSING_POOL)
    assert "Open source:" not in prefix
    assert "gh-a" in prefix


async def test_a_pool_with_open_source_still_lists_it():
    pool = CVPool(
        experiences=NURSING_POOL.experiences,
        open_source=(PoolBullet("oss-1", ("tools",), "Maintained a clinical checklist"),),
        summary_facts=NURSING_POOL.summary_facts,
    )
    prefix = await _prefix_sent(pool)
    assert "Open source:" in prefix
    assert "oss-1" in prefix
