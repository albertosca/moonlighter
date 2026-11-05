"""Pins reevaluation_batch's own surface: the settings and tally objects and a batch driven without main()."""

import asyncio
import contextlib
import dataclasses
from unittest.mock import MagicMock

import pytest
import reevaluation_batch
from moonlighter.core.db import Job, init_db
from moonlighter.core.llm.spend_limit import is_spend_limit
from reevaluation_batch import ReevaluationSettings, Tally, reevaluate

from tests.scripts.reevaluate_bug_victims.harness import Evaluator, rows, victim


@pytest.fixture(autouse=True)
def _database(temporary_database):
    init_db()


def _settings(**changes) -> ReevaluationSettings:
    fields = {
        "model": "m",
        "profile": {"name": "Ana"},
        "threshold": 6.5,
        "title_blocklist": [],
        "dry_run": False,
        "title_only": False,
        "concurrency": 2,
    }
    return ReevaluationSettings(**{**fields, **changes})


def _run(monkeypatch, jobs, settings, *, evaluator) -> MagicMock:
    factory = MagicMock(return_value="CALLER")
    monkeypatch.setattr(reevaluation_batch, "make_caller", factory)
    monkeypatch.setattr(reevaluation_batch, "evaluate_job", evaluator)
    asyncio.run(reevaluate(jobs, {"cfg": 1}, settings))
    return factory


def test_the_settings_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _settings().model = "other"


def test_a_tally_starts_at_zero_and_is_mutable():
    tally = Tally()

    tally.errors += 1

    assert dataclasses.astuple(tally) == (0, 0, 0, 1, False)


def test_the_caller_is_built_from_the_config_and_handed_to_every_evaluation(monkeypatch):
    jobs = [victim("Acme", "One"), victim("Acme", "Two")]
    evaluator = Evaluator({}, suspend=False)

    factory = _run(monkeypatch, jobs, _settings(), evaluator=evaluator)

    factory.assert_called_once_with({"cfg": 1})
    assert [call["_caller"] for call in evaluator.calls] == ["CALLER", "CALLER"]
    assert [call["profile"] for call in evaluator.calls] == [{"name": "Ana"}] * 2


def test_the_threshold_comes_from_the_settings(monkeypatch):
    jobs = [victim("Acme", "One")]
    evaluator = Evaluator({}, suspend=False)

    _run(monkeypatch, jobs, _settings(threshold=1.0), evaluator=evaluator)

    assert rows()[0][-1] == "new"


def test_a_spend_limit_error_is_recognised_by_the_shared_predicate(monkeypatch, capsys):
    error = RuntimeError("You've hit your spend limit")
    assert is_spend_limit(error)
    jobs = [victim("Acme", "One"), victim("Acme", "Two")]
    evaluator = Evaluator({"One": error}, suspend=True)

    _run(monkeypatch, jobs, _settings(concurrency=1), evaluator=evaluator)

    output = capsys.readouterr().out
    assert "SPEND LIMIT reached" in output
    assert "Re-evaluation interrupted by spend limit." in output
    assert [call["title"] for call in evaluator.calls] == ["One"]
    assert Job.select().where(Job.score_notes.startswith("reevaluate_error")).count() == 0


def test_the_whole_batch_runs_inside_the_reevaluate_operation_metrics(monkeypatch):
    events = []

    @contextlib.contextmanager
    def recording(name):
        events.append(("enter", name))
        yield
        events.append(("exit", name))

    class Marking(Evaluator):
        async def __call__(self, *positional, **keywords):
            events.append(("evaluate", None))
            return await super().__call__(*positional, **keywords)

    monkeypatch.setattr(reevaluation_batch, "operation_metrics", recording)

    _run(monkeypatch, [victim("Acme", "One")], _settings(), evaluator=Marking({}, suspend=False))

    assert events == [("enter", "reevaluate"), ("evaluate", None), ("exit", "reevaluate")]
