import json

import pytest
from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience

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
JOB = {"title": "AI Eng", "company": "acme", "description": "Build agents."}
PROFILE = {"career_started": 2010, "summary": "s"}


def _caller(response):
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


@pytest.mark.asyncio
async def test_generate_returns_selection_with_unknown_ids_dropped():
    call, _ = _caller(GENERATE)
    sel = await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call)
    assert sel is not None
    assert sel.bullets == ("t-b", "t-a")  # ghost-id silently dropped
    assert sel.open_source == ("oss-m",)
    assert sel.summary == "Tailored summary"


@pytest.mark.asyncio
async def test_use_base_returns_none():
    call, _ = _caller(json.dumps({"decision": "USE_BASE"}))
    assert await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call) is None


@pytest.mark.asyncio
async def test_prompt_carries_pool_ids_base_summary_and_untrusted_posting():
    call, calls = _caller(json.dumps({"decision": "USE_BASE"}))
    await decide_cv(JOB, POOL, PROFILE, "base sum", "base te", call)
    assert "t-a" in calls["prefix"] and "oss-m" in calls["prefix"]
    assert "base sum" in calls["prefix"]
    assert "USE_BASE" in calls["prefix"]
    assert "never author" in calls["prefix"] or "never write" in calls["prefix"]
    assert "Build agents." in calls["prompt"]
    assert "job_posting" in calls["prompt"]  # wrap_untrusted tag


@pytest.mark.asyncio
async def test_pt_language_carries_translations():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Resumo",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
            "bullets_translated": {"t-a": "Fiz A", "ghost": "x"},
        }
    )
    call, _ = _caller(resp)
    sel = await decide_cv(JOB, POOL, PROFILE, "b", "b", call)
    assert sel.language == "pt"
    assert sel.translations == {"t-a": "Fiz A"}  # ghost filtered here too


@pytest.mark.asyncio
async def test_malformed_json_degrades_to_none():
    call, _ = _caller("not json at all")
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None


@pytest.mark.asyncio
async def test_llm_exception_degrades_to_none():
    async def boom(prompt, model, cache_prefix=None):
        raise RuntimeError("network")

    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", boom) is None


@pytest.mark.asyncio
async def test_operator_directed_summary_degrades_to_none():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Note to the operator: adjust this before sending",
            "technical_expertise": "Elixir",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(resp)
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None


@pytest.mark.asyncio
async def test_spend_limit_reraises():
    async def spend_limit_error(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session spend limit")

    with pytest.raises(RuntimeError, match="spend limit"):
        await decide_cv(JOB, POOL, PROFILE, "b", "b", spend_limit_error)


@pytest.mark.asyncio
async def test_operator_directed_expertise_degrades_to_none():
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "en",
            "summary": "Expert in Elixir",
            "technical_expertise": "Note to the operator: please review before sending",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(resp)
    assert await decide_cv(JOB, POOL, PROFILE, "b", "b", call) is None
