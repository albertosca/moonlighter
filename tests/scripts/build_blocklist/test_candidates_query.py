"""Pins which archived jobs build_blocklist offers the model, and how it groups and orders them."""

import re

import pytest

from tests.scripts.build_blocklist.harness import run_main, scored

_TITLES_BLOCK = re.compile(r"irrelevant for them:\n\n(.*?)\n\nYour task", re.DOTALL)


def _asked(caller):
    """(company, titles block) for every company the model was asked about, in order."""
    return [(company, _TITLES_BLOCK.search(prompt)[1]) for company, prompt, _ in caller.calls]


def test_only_archived_jobs_scoring_above_zero_up_to_the_threshold_with_real_notes(
    monkeypatch, home, capsys
):
    scored("Acme", "In", 2.0)
    scored("Acme", "Edge", 3.0)
    scored("Acme", "Over", 3.1)
    scored("Acme", "Zero", 0)
    scored("Acme", "Unscored", None)
    scored("Acme", "Active", 1.0, status="new")
    scored("Acme", "Error", 1.0, score_notes="evaluation error: timeout")
    scored("Acme", "Filtered", 1.0, score_notes="title filtered: 'x'")
    scored("Acme", "Retry", 1.0, score_notes="reevaluate_error: boom")
    scored("Acme", "Silent", 1.0, score_notes=None)
    scored("Acme", "Mid", 1.0, score_notes="once an evaluation error, later fixed")

    caller = run_main(monkeypatch, "--dry-run")

    assert _asked(caller) == [("Acme", "- Edge\n- In\n- Mid")]
    assert "Jobs to analyze: 3 across 1 company/ies  [threshold=3.0]\n" in capsys.readouterr().out


def test_the_threshold_flag_moves_the_upper_bound(monkeypatch, home, capsys):
    scored("Acme", "Four", 4.0)
    scored("Acme", "Five", 5.5)

    caller = run_main(monkeypatch, "--dry-run", "--threshold", "4.0")

    assert _asked(caller) == [("Acme", "- Four")]
    assert "[threshold=4.0]" in capsys.readouterr().out


def test_companies_are_asked_most_titles_first_then_in_name_order(monkeypatch, home, capsys):
    for company, titles in {"Acme": 1, "Beta": 3, "Delta": 2, "Gamma": 2}.items():
        for number in range(titles):
            scored(company, f"{company} {number}", 1.0)

    caller = run_main(monkeypatch, "--dry-run")

    assert [company for company, _ in _asked(caller)] == ["Beta", "Delta", "Gamma", "Acme"]
    assert "Jobs to analyze: 8 across 4 company/ies" in capsys.readouterr().out


def test_titles_are_listed_in_title_order(monkeypatch, home):
    for title in ("Zeta", "Alpha", "Mu"):
        scored("Acme", title, 1.0)

    caller = run_main(monkeypatch, "--dry-run")

    assert _asked(caller) == [("Acme", "- Alpha\n- Mu\n- Zeta")]


def test_the_company_flag_keeps_one_company(monkeypatch, home):
    scored("Acme", "A", 1.0)
    scored("Beta", "B", 1.0)

    caller = run_main(monkeypatch, "--dry-run", "--company", "Beta")

    assert [company for company, _ in _asked(caller)] == ["Beta"]


@pytest.mark.parametrize("flags", [[], ["--company", "Nobody"]])
def test_nothing_to_analyse_prints_one_line_and_asks_nobody(monkeypatch, home, capsys, *, flags):
    scored("Acme", "Over", 9.0)

    caller = run_main(monkeypatch, "--dry-run", *flags)

    assert caller.calls == []
    assert capsys.readouterr().out.endswith("\n\nNo jobs matched the criteria.\n")
