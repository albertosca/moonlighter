"""Shared inputs for the tests of the model's selection call."""

import json

from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience

POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Dev",
            period="2023 -- 2026",
            location="BH",
            bullets=(PoolBullet("t-a", ("backend",), "A"), PoolBullet("t-b", ("ai",), "B")),
            prose="Taught ML",
            prose_id="trybe-prose",
            angles=(),
        ),
        PoolExperience(
            company="IGTI",
            title="Professor",
            period="2018 -- 2019",
            location="BH",
            bullets=(PoolBullet("igti-b", ("ml",), "C"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(PoolBullet("oss-m", ("ai",), "M"),),
    summary_facts=("compute years from career_started",),
)


AI_ENGINEER_JOB = {"title": "AI Eng", "company": "acme", "description": "Build agents."}


PROFILE = {"career_started": 2010, "summary": "s"}


def recording_caller(response):
    calls = {}

    async def call(prompt, model, cache_prefix=None):
        calls["prompt"] = prompt
        calls["prefix"] = cache_prefix
        return response

    return call, calls


GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "Tailored summary",
        "technical_expertise": "Elixir",
        "bullets": ["t-b", "ghost-id", "t-a"],
        "open_source": ["oss-m"],
    }
)


BARE_TEMPLATE = "%%SUMMARY%%\n%%TECHNICAL_EXPERTISE%%\n%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"


def pt_response(translation, bullet_id="igti-b"):  # igti-b: a bullets-only entry
    return json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": [bullet_id],
            "open_source": [],
            "bullets_translated": {bullet_id: translation},
        }
    )


WIDE_POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Dev",
            period="2023 -- 2026",
            location="BH",
            bullets=tuple(
                PoolBullet(f"b-{index}", ("backend",), f"B{index}") for index in range(12)
            ),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        POOL.experiences[0],  # carries trybe-prose
    ),
    open_source=(PoolBullet("oss-1", ("ai",), "M1"), PoolBullet("oss-2", ("ai",), "M2")),
    summary_facts=(),
)
