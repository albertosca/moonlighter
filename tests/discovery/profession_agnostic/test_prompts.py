"""The candidate's identity comes from the profile, never from the code (#120): the prompts.

Idea credit: JR2PROJETOS (`profession-agnostic` branch on their fork); the code is ours.
Every test here inspects the text actually sent to a fake LLM caller.
"""

import pytest

from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.engagement import engagement_section
from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluation.single import evaluate_job
from tests.discovery.profession_agnostic.fake_callers import (
    BATCH_RESPONSE,
    NURSE_PROFILE,
    SINGLE_RESPONSE,
    spy,
)

# Words that would betray a hardcoded software-engineer, Brazilian, permanent-role candidate.
FORBIDDEN = (
    "software",
    "engineer",
    "brazil",
    "latam",
    "permanent full-time",
    "technical expertise",
)


def _assert_no_hardcoded_identity(text):
    lowered = text.lower()
    for word in FORBIDDEN:
        assert word not in lowered, f"{word!r} leaked into a prompt for a nurse profile"


async def test_single_evaluation_prompt_has_no_software_identity():
    caller, seen = spy(SINGLE_RESPONSE)
    await evaluate_job(
        "Hospital", "ICU Nurse", "Care for patients.", NURSE_PROFILE, "m", caller,
        location="Lisbon", remote_type="onsite",
    )  # fmt: skip
    _assert_no_hardcoded_identity(seen["prefix"])
    assert "Registered Nurse" in seen["prefix"]
    assert "described below" in seen["prefix"]
    assert "## Engagement type" not in seen["prefix"]


async def test_batch_evaluation_prompt_has_no_software_identity():
    caller, seen = spy(BATCH_RESPONSE)
    jobs = [EvalInput("Hospital", "ICU Nurse", "Care."), EvalInput("Clinic", "Nurse", "Care.")]
    await evaluate_jobs_batch(jobs, NURSE_PROFILE, "m", caller=caller)
    _assert_no_hardcoded_identity(seen["prefix"])
    assert "## Engagement type" not in seen["prefix"]


async def test_the_engagement_the_profile_names_reaches_both_prompts():
    profile = {**NURSE_PROFILE, "preferences": {"engagement": "part-time hospital"}}
    caller, seen = spy(SINGLE_RESPONSE)
    await evaluate_job(
        "Hospital", "Nurse", "Care.", profile, "m", caller, location=None, remote_type=None
    )
    assert "targets part-time hospital positions" in seen["prefix"]
    caller, seen = spy(BATCH_RESPONSE)
    await evaluate_jobs_batch(
        [EvalInput("A", "B", "C"), EvalInput("D", "E", "F")], profile, "m", caller=caller
    )
    assert "targets part-time hospital positions" in seen["prefix"]


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"preferences": None},
        {"preferences": {}},
        {"preferences": {"engagement": ""}},
        {"preferences": {"engagement": "   "}},
        {"preferences": {"engagement": 3}},
    ],
)
def test_engagement_unknown_means_no_section(profile):
    assert engagement_section(profile) == ""


def test_engagement_text_is_inserted_verbatim_even_with_braces():
    section = engagement_section({"preferences": {"engagement": "{weird} full-time"}})
    assert "targets {weird} full-time positions" in section
