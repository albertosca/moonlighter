"""Pins the prompt build_blocklist sends for a company: profile fallbacks, the four-skill cut and the 80-title cap."""

import pytest

from tests.scripts.build_blocklist.harness import run_main, scored

FULL_PROFILE = {
    "name": "Ana",
    "level": "staff engineer",
    "top_skills": ["Elixir", "Phoenix", "PostgreSQL", "Rust", "Go", "Python"],
}


def _prompt_for_acme(monkeypatch, **options) -> str:
    caller = run_main(monkeypatch, "--dry-run", **options)
    assert [company for company, _, _ in caller.calls] == ["Acme"]
    return caller.calls[0][1]


def test_prompt_without_a_profile_uses_the_generic_candidate(monkeypatch, home, snapshot_text):
    scored("Acme", "Recruiter Lead", 1.0)
    scored("Acme", "Office Manager", 2.5)

    snapshot_text(_prompt_for_acme(monkeypatch), "no_profile")


def test_prompt_with_a_full_profile_cuts_skills_to_four_and_titles_to_eighty(
    monkeypatch, home, snapshot_text
):
    for number in range(85):
        scored("Acme", f"Title {number:02d}", 1.0)

    snapshot_text(_prompt_for_acme(monkeypatch, profile=FULL_PROFILE), "full_profile")


@pytest.mark.parametrize("skills", [[], None])
def test_prompt_falls_back_to_software_engineering_without_skills(monkeypatch, home, skills):
    scored("Acme", "Recruiter Lead", 1.0)

    prompt = _prompt_for_acme(monkeypatch, profile={"top_skills": skills})

    assert prompt.startswith(
        "You are building a job title blocklist for the candidate, "
        "a senior software engineer specializing in software engineering.\n"
    )
