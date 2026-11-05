"""Tests for the regional eligibility section of both prompt prefixes."""

from moonlighter.discovery.evaluation.batch import evaluate_jobs_batch
from moonlighter.discovery.evaluation.models import EvalInput
from moonlighter.discovery.evaluation.regional_eligibility import (
    LOCATION_PRECEDENCES,
    regional_eligibility_section,
)
from moonlighter.discovery.evaluation.single import evaluate_job


async def test_eval_prefixes_name_no_city():
    # The regional rule used to say "The candidate works from Belo Horizonte",
    # capping every non-Brazil posting at 2.0 for any user. Where the candidate
    # lives belongs to their profile (criteria), never to the prompt.
    # The section is rendered per profile now, so check what the model receives.
    for profile in ({}, {"criteria": {"location_precedence": "generic"}}):
        for prefix in await _prefixes_for(profile):
            assert "Belo Horizonte" not in prefix
            assert "Brazil" not in prefix
            assert "## Regional eligibility" in prefix


async def _prefixes_for(profile):
    captured = {}

    async def caller(prompt, model, cache_prefix=None):
        captured.setdefault("single", cache_prefix)
        return '{"score": 5.0, "score_notes": "x", "caveats": []}'

    async def batch_caller(prompt, model, cache_prefix=None):
        captured.setdefault("batch", cache_prefix)
        return '[{"score": 5.0, "score_notes": "x", "caveats": []}, {"score": 5.0, "score_notes": "x", "caveats": []}]'

    await evaluate_job("Co", "Eng", "desc", profile, "m", caller, location=None, remote_type=None)
    await evaluate_jobs_batch(
        [EvalInput("Co", "A", "d"), EvalInput("Co", "B", "d")], profile, "m", caller=batch_caller
    )
    return captured["single"], captured["batch"]


async def test_by_default_a_posting_specific_location_beats_a_generic_remote_claim():
    for prefix in await _prefixes_for({"skills": ["python"]}):
        assert "posting-specific location paragraph wins" in prefix


async def test_the_profile_can_let_the_generic_remote_claim_win():
    profile = {"criteria": {"location_precedence": "generic"}}
    for prefix in await _prefixes_for(profile):
        assert "generic company-wide remote claim wins" in prefix
        assert "posting-specific location paragraph wins" not in prefix


async def test_required_fluency_in_a_language_the_profile_lacks_is_a_hard_filter():
    for prefix in await _prefixes_for({"languages": ["Portuguese", "English"]}):
        assert "fluency in a language the candidate's profile does not list" in prefix


def test_the_location_precedences_keep_their_order_because_startup_prints_them():
    assert LOCATION_PRECEDENCES == ("specific", "generic")


def test_an_unknown_location_precedence_falls_back_to_specific():
    unknown = {"criteria": {"location_precedence": "bogus"}}
    assert regional_eligibility_section(unknown) == regional_eligibility_section({})
    assert regional_eligibility_section(
        {"criteria": "not a mapping"}
    ) == regional_eligibility_section({})
