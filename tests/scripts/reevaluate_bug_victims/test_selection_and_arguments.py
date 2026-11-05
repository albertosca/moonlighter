"""Pins which jobs reevaluate_bug_victims picks and what it passes to the evaluator for each flag and config value."""

import pytest
from moonlighter.discovery.evaluation.models import EvaluationResult

from tests.scripts.reevaluate_bug_victims.harness import CONFIG, rows, run_main, victim


def test_no_victims_prints_one_line_and_never_builds_a_caller(monkeypatch, caller_factory, capsys):
    victim("Acme", "Scored", score=1.0)
    victim("Acme", "Not archived", status="new")
    victim("Acme", "Other notes", score_notes="evaluation error: timeout")
    victim("Acme", "No notes", score_notes=None)

    run_main(monkeypatch)

    assert capsys.readouterr().out == "No jobs with bug signature found.\n"
    caller_factory.assert_not_called()


@pytest.mark.parametrize(
    ("flags", "titles"),
    [
        (["--limit", "3"], ["A1", "A2", "A3"]),
        (["--limit", "0"], ["A1", "A2", "A3", "B1", "B2"]),
        (["--company", "Beta"], ["B1", "B2"]),
        (["--company", "Acme", "--limit", "2"], ["A1", "A2"]),
    ],
)
def test_limit_and_company_select_in_company_then_id_order(
    monkeypatch, caller_factory, *, flags, titles
):
    for company, title in [
        ("Beta", "B1"),
        ("Beta", "B2"),
        ("Acme", "A1"),
        ("Acme", "A2"),
        ("Acme", "A3"),
    ]:
        victim(company, title)

    evaluator = run_main(monkeypatch, "--concurrency", "1", *flags)

    assert [call["title"] for call in evaluator.calls] == titles


@pytest.mark.parametrize(
    ("flags", "description", "sent"),
    [
        ([], "Full text", "Full text"),
        ([], None, "Dev at Acme"),
        ([], "", "Dev at Acme"),
        (["--title-only"], "Full text", "Dev"),
    ],
)
def test_the_description_sent_to_the_model(
    monkeypatch, caller_factory, *, flags, description, sent
):
    victim("Acme", "Dev", description=description)

    evaluator = run_main(monkeypatch, *flags)

    assert [call["description"] for call in evaluator.calls] == [sent]


@pytest.mark.parametrize(
    ("flags", "mode"), [([], "full description"), (["--title-only"], "title-only")]
)
def test_the_summary_names_the_mode_and_the_default_concurrency(
    monkeypatch, caller_factory, capsys, *, flags, mode
):
    victim("Acme", "Dev")

    run_main(monkeypatch, *flags)

    assert f"Result: 1 jobs found  [{mode}] concurrency=5\n" in capsys.readouterr().out


def test_every_argument_reaches_evaluate_job(monkeypatch, caller_factory):
    victim("Acme", "Dev", location="Remote, BR", remote_type="remote")
    victim("Acme", "Ops")

    evaluator = run_main(monkeypatch, "--concurrency", "1")

    caller = caller_factory.return_value
    caller_factory.assert_called_once_with(CONFIG)
    shared = {"company": "Acme", "profile": {"name": "Ana"}, "model": "m-eval", "_caller": caller}
    assert evaluator.calls == [
        {
            **shared,
            "title": "Dev",
            "description": "Dev at Acme",
            "location": "Remote, BR",
            "remote_type": "remote",
        },
        {
            **shared,
            "title": "Ops",
            "description": "Ops at Acme",
            "location": None,
            "remote_type": None,
        },
    ]


@pytest.mark.parametrize(
    ("flags", "config", "model"),
    [
        (["--model", "cli"], {"eval_model": "e", "llm_model": "l"}, "cli"),
        ([], {"eval_model": "e", "llm_model": "l"}, "e"),
        ([], {"llm_model": "l"}, "l"),
        ([], {}, "claude-haiku-4-5-20251001"),
    ],
)
def test_the_model_comes_from_the_flag_then_eval_model_then_llm_model(
    monkeypatch, caller_factory, *, flags, config, model
):
    victim("Acme", "Dev")

    evaluator = run_main(monkeypatch, *flags, config=config)

    assert evaluator.calls[0]["model"] == model


def test_the_threshold_comes_from_config_and_defaults_to_six_and_a_half(
    monkeypatch, caller_factory
):
    victim("Acme", "Edge")
    victim("Acme", "Below")
    outcomes = {
        "Edge": EvaluationResult(score=6.5, score_notes="edge"),
        "Below": EvaluationResult(score=6.4, score_notes="below"),
    }

    run_main(monkeypatch, "--concurrency", "1", outcomes=outcomes, config={})

    assert [row[8] for row in rows()] == ["new", "archived"]
