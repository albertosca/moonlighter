"""The tailored-CV prompt names no profession and no section the pool lacks (#120)."""

import json

from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience

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
JOB = {"title": "ICU Nurse", "company": "Clinic", "description": "Care for patients."}


async def _prefix_sent(pool):
    seen = {}

    async def caller(prompt, model, cache_prefix=None):
        seen["prefix"] = cache_prefix
        return json.dumps({"decision": "USE_BASE"})

    await decide_cv(JOB, pool, {"career_started": 2016}, "base summary", "base line", caller)
    return seen["prefix"]


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
