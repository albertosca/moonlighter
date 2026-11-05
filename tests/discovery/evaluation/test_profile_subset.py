"""Tests for the evaluation profile subset the scoring prompt carries."""

from moonlighter.discovery.evaluation.profile_subset import profile_for_eval


def test_profile_for_eval_keeps_scoring_keys():
    profile = {
        "name": "X",
        "phone": "1",
        "email": "e",
        "linkedin": "l",
        "education": [],
        "publications": [],
        "criteria": {"hard_filters": ["no .NET"]},
        "skills": ["python"],
        "headline": "Staff",
        "summary": "...",
        "preferences": {"salary_min_usd": 150000},
        "languages": ["pt", "en"],
        "experience": [{"role": "X"}],
        "open_source": [{"name": "moonlighter", "notes": "Built spec-driven with Claude Code"}],
    }
    trimmed = profile_for_eval(profile)
    assert set(trimmed) == {
        "criteria",
        "skills",
        "headline",
        "summary",
        "preferences",
        "languages",
        "experience",
        # Public projects are evidence of skills a posting may require (Encora #8314,
        # 2026-09-24: "Claude Code not documented" while open_source said it).
        "open_source",
    }
    assert "email" not in trimmed
    assert "phone" not in trimmed


def test_profile_for_eval_tolerates_missing_keys():
    assert profile_for_eval({"skills": ["go"]}) == {"skills": ["go"]}
    assert profile_for_eval({}) == {}
