import json

import blocklist_proposals
import pytest


def _caller(answer, seen=None):
    async def caller(prompt, model):
        if seen is not None:
            seen.append((prompt, model))
        if isinstance(answer, Exception):
            raise answer
        return answer

    return caller


def test_the_quota_markers_are_exactly_these():
    assert blocklist_proposals.QUOTA_MARKERS == (
        "spend limit",
        "quota",
        "rate limit",
        "too many requests",
        "overloaded",
        "429",
        "usage limit",
    )


@pytest.mark.parametrize("marker", blocklist_proposals.QUOTA_MARKERS)
def test_every_quota_marker_is_recognised_in_any_case(marker):
    assert blocklist_proposals.is_quota_error(RuntimeError(f"Request failed: {marker.upper()}!"))


@pytest.mark.parametrize("message", ["connection reset", "", "Expecting value: line 1 column 1"])
def test_other_errors_are_not_quota_errors(message):
    assert not blocklist_proposals.is_quota_error(ValueError(message))


def test_the_prompt_names_the_company_the_threshold_and_the_profile():
    profile = {"name": "Ana", "level": "staff engineer", "top_skills": ["a", "b", "c", "d", "e"]}

    prompt = blocklist_proposals.proposal_prompt("Acme", ["T1", "T2"], 2.5, profile=profile)

    assert prompt.startswith(
        "You are building a job title blocklist for Ana, a staff engineer specializing in a, b, c, d."
    )
    assert "titles at **Acme** were evaluated and scored 2.5 or below out of 10" in prompt
    assert "\n\n- T1\n- T2\n\nYour task:" in prompt


def test_the_prompt_defaults_each_missing_profile_field_on_its_own():
    prompt = blocklist_proposals.proposal_prompt("Acme", [], 3.0, profile={"top_skills": []})

    assert prompt.startswith(
        "You are building a job title blocklist for the candidate, a senior software engineer "
        "specializing in software engineering."
    )
    assert "out of 10 — meaning they are clearly irrelevant for them:\n\n\n\nYour task" in prompt


def test_only_the_first_eighty_titles_reach_the_prompt():
    titles = [f"Title {number:02d}" for number in range(81)]

    prompt = blocklist_proposals.proposal_prompt("Acme", titles, 3.0, profile={})

    assert "- Title 79\n" in prompt
    assert "Title 80" not in prompt


async def test_only_safe_entries_with_a_pattern_are_returned_in_order():
    answer = [
        {"pattern": "b", "safe": True},
        {"pattern": "a", "safe": False},
        {"pattern": "c", "safe": "true"},
        {"pattern": "", "safe": True},
        {"safe": True},
        "text",
        {"pattern": "d", "safe": True},
    ]
    seen = []

    result = await blocklist_proposals.propose_for_company(
        "Acme",
        "the prompt",
        caller=_caller("```json\n" + json.dumps(answer) + "\n```", seen),
        model="m",
    )

    assert result == [{"pattern": "b", "safe": True}, {"pattern": "d", "safe": True}]
    assert seen == [("the prompt", "m")]


async def test_an_answer_that_is_not_a_list_gives_nothing():
    result = await blocklist_proposals.propose_for_company(
        "Acme", "p", caller=_caller('{"pattern": "x", "safe": true}'), model="m"
    )

    assert result == []


async def test_a_json_scalar_gives_nothing_without_a_warning(capsys):
    result = await blocklist_proposals.propose_for_company(
        "Acme", "p", caller=_caller("42"), model="m"
    )

    assert result == []
    assert capsys.readouterr().out == ""


async def test_a_failure_is_printed_with_the_company_and_gives_nothing(capsys):
    result = await blocklist_proposals.propose_for_company(
        "Acme", "p", caller=_caller(RuntimeError("connection reset")), model="m"
    )

    assert result == []
    assert capsys.readouterr().out == "  ⚠️  Error processing Acme: connection reset\n"


async def test_a_quota_error_is_raised_and_printed_nothing(capsys):
    with pytest.raises(RuntimeError, match="Spend Limit"):
        await blocklist_proposals.propose_for_company(
            "Acme", "p", caller=_caller(RuntimeError("Spend Limit reached")), model="m"
        )

    assert capsys.readouterr().out == ""
