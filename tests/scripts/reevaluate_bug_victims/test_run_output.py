"""Pins what a reevaluate_bug_victims run prints and writes: a mixed run, a dry run and a spend-limit stop."""

from moonlighter.discovery.evaluation.models import EvaluationResult
from tests.scripts.reevaluate_bug_victims.harness import (
    BUG,
    UNTOUCHED_NOTES,
    labeller,
    rows,
    run_main,
    victim,
)


def test_a_mixed_run_prints_and_persists_every_outcome(monkeypatch, caller_factory, capsys):
    victim("Acme", "Recruiter Lead")
    victim("Acme", "Backend Engineer")
    victim("Acme", "QA Tester", caveats="old")
    victim("Beta", "Platform Engineer")
    promoted = EvaluationResult(
        score=6.5,
        score_notes="fits",
        caveats=["c1"],
        salary_min=100,
        salary_max=200,
        salary_currency="USD",
        salary_source="stated",
    )
    outcomes = {
        "Backend Engineer": promoted,
        "QA Tester": EvaluationResult(score=2.5, score_notes="weak"),
        "Platform Engineer": RuntimeError("boom"),
    }

    run_main(monkeypatch, "--concurrency", "1", outcomes=outcomes)

    label = labeller(4)
    assert capsys.readouterr().out == (
        "Jobs found: 4  |  model: m-eval\n"
        "  Acme                : 3\n"
        "  Beta                : 1\n"
        f"{label(1, 'Acme', 'Recruiter Lead')} -- skip title ('recruiter')\n"
        f"{label(2, 'Acme', 'Backend Engineer')} ↑ NEW score=6.5\n"
        f"{label(3, 'Acme', 'QA Tester')}   arq score=2.5\n"
        f"{label(4, 'Beta', 'Platform Engineer')} ✗ ERROR: boom\n"
        "\n"
        "Result: 4 jobs found  [full description] concurrency=1\n"
        "  -- skipped by title:       1\n"
        "  ↑ promoted to 'new':       1\n"
        "     remain archived:        1\n"
        "  ✗ errors:                  1\n"
        "  LLM calls (m-eval):      3\n"
    )
    nothing = (None, None, None, None)
    assert rows() == [
        ("Recruiter Lead", 0.0, "title filtered: 'recruiter'", "[]", *nothing, "archived"),
        ("Backend Engineer", 6.5, "fits", '["c1"]', 100, 200, "USD", "stated", "new"),
        ("QA Tester", 2.5, "weak", "[]", *nothing, "archived"),
        ("Platform Engineer", 0.0, "reevaluate_error: boom", None, *nothing, "archived"),
    ]


def test_a_dry_run_changes_no_row_and_says_so(monkeypatch, caller_factory, capsys):
    victim("Acme", "Recruiter Lead")
    victim("Acme", "Backend Engineer")
    victim("Beta", "Platform Engineer")
    before = rows()
    outcomes = {
        "Backend Engineer": EvaluationResult(score=9.0, score_notes="fits"),
        "Platform Engineer": RuntimeError("boom"),
    }

    run_main(monkeypatch, "--dry-run", "--concurrency", "1", outcomes=outcomes)

    assert rows() == before
    label = labeller(3)
    assert capsys.readouterr().out == (
        "Jobs found: 3  |  model: m-eval\n"
        "  Acme                : 2\n"
        "  Beta                : 1\n"
        "\n⚠️  DRY RUN — no changes will be saved.\n\n"
        f"{label(1, 'Acme', 'Recruiter Lead')} -- skip title ('recruiter')\n"
        f"{label(2, 'Acme', 'Backend Engineer')} ↑ NEW score=9.0\n"
        f"{label(3, 'Beta', 'Platform Engineer')} ✗ ERROR: boom\n"
        "\n"
        "[DRY RUN] Result: 3 jobs found  [full description] concurrency=1\n"
        "  -- skipped by title:       1\n"
        "  ↑ promoted to 'new':       1\n"
        "     remain archived:        0\n"
        "  ✗ errors:                  1\n"
        "  LLM calls (m-eval):      2\n"
    )


def test_a_spend_limit_stops_the_jobs_that_have_not_started(monkeypatch, caller_factory, capsys):
    for number in range(1, 6):
        victim("Acme", f"Job {number}")
    outcomes = {
        "Job 1": EvaluationResult(score=7.0, score_notes="ok"),
        "Job 2": RuntimeError("You've hit your spend limit"),
        "Job 3": EvaluationResult(score=3.0, score_notes="meh"),
    }

    evaluator = run_main(monkeypatch, "--concurrency", "3", outcomes=outcomes)

    assert [call["title"] for call in evaluator.calls] == ["Job 1", "Job 2", "Job 3"]
    label = labeller(5)
    assert capsys.readouterr().out == (
        "Jobs found: 5  |  model: m-eval\n"
        "  Acme                : 5\n"
        f"{label(1, 'Acme', 'Job 1')} ↑ NEW score=7.0\n"
        f"{label(2, 'Acme', 'Job 2')} 🚫 SPEND LIMIT reached — stopping. Error: You've hit your spend limit\n"
        f"{label(3, 'Acme', 'Job 3')}   arq score=3.0\n"
        "\n🚫 Re-evaluation interrupted by spend limit.\n"
        "\n"
        "Result: 5 jobs found  [full description] concurrency=3\n"
        "  -- skipped by title:       0\n"
        "  ↑ promoted to 'new':       1\n"
        "     remain archived:        1\n"
        "  ✗ errors:                  0\n"
        "  LLM calls (m-eval):      5\n"
    )
    assert [row[2] for row in rows()] == [
        "ok",
        UNTOUCHED_NOTES,
        "meh",
        UNTOUCHED_NOTES,
        UNTOUCHED_NOTES,
    ]


def test_a_title_skip_still_prints_after_a_spend_limit_stop(monkeypatch, caller_factory, capsys):
    victim("Acme", "Job 1")
    victim("Acme", "Recruiter 2")
    victim("Acme", "Job 3")

    evaluator = run_main(
        monkeypatch,
        "--concurrency",
        "1",
        outcomes={"Job 1": RuntimeError("quota exceeded: spend limit")},
        suspend=False,
    )

    assert [call["title"] for call in evaluator.calls] == ["Job 1"]
    label = labeller(3)
    assert capsys.readouterr().out == (
        "Jobs found: 3  |  model: m-eval\n"
        "  Acme                : 3\n"
        f"{label(1, 'Acme', 'Job 1')} 🚫 SPEND LIMIT reached — stopping. Error: quota exceeded: spend limit\n"
        f"{label(2, 'Acme', 'Recruiter 2')} -- skip title ('recruiter')\n"
        "\n🚫 Re-evaluation interrupted by spend limit.\n"
        "\n"
        "Result: 3 jobs found  [full description] concurrency=1\n"
        "  -- skipped by title:       1\n"
        "  ↑ promoted to 'new':       0\n"
        "     remain archived:        0\n"
        "  ✗ errors:                  0\n"
        "  LLM calls (m-eval):      2\n"
    )


def test_a_long_error_is_stored_truncated_to_200_characters(monkeypatch, caller_factory):
    victim("Acme", "Dev")

    run_main(monkeypatch, outcomes={"Dev": RuntimeError("x" * 300)})

    assert rows()[0][2] == "reevaluate_error: " + "x" * 200


def test_a_long_title_is_cut_to_55_characters_in_the_label(monkeypatch, caller_factory, capsys):
    victim("Acme", "T" * 60)

    run_main(monkeypatch)

    assert f"[   1/1] [Acme] {'T' * 55}   arq score=1.0\n" in capsys.readouterr().out


def test_the_bug_marker_is_the_exact_prefix_victims_carry():
    assert BUG == "evaluation error: claude CLI exited with code 1"
