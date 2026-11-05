"""Shared pieces of the reevaluate_bug_victims pins: the fake evaluator, seeded rows and the main() driver."""

import asyncio
import itertools
import sys
from collections.abc import Callable
from unittest.mock import patch

import reevaluate_bug_victims
from moonlighter.core.db import Job
from moonlighter.discovery.evaluation.models import EvaluationResult

BUG = reevaluate_bug_victims.BUG_MARKER
UNTOUCHED_NOTES = f"{BUG} (stdin)"
CONFIG = {"title_blocklist": ["recruiter"], "eval_model": "m-eval"}
_URLS = itertools.count(1)


class Evaluator:
    """Stands in for evaluate_job with its real keyword signature; suspends once per call unless told not to."""

    def __init__(self, outcomes: dict[str, object], *, suspend: bool) -> None:
        self.outcomes = outcomes
        self.suspend = suspend
        self.calls: list[dict[str, object]] = []

    async def __call__(  # noqa: PLR0913, PLR0917 - mirrors evaluate_job's signature
        self, company, title, description, profile, model, _caller, *, location, remote_type
    ):
        self.calls.append(
            {
                "company": company,
                "title": title,
                "description": description,
                "profile": profile,
                "model": model,
                "_caller": _caller,
                "location": location,
                "remote_type": remote_type,
            }
        )
        if self.suspend:
            await asyncio.sleep(0)
        outcome = self.outcomes.get(title, EvaluationResult(score=1.0, score_notes="low"))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def victim(company: str, title: str, **fields) -> Job:
    defaults = {
        "source": "greenhouse",
        "url": f"https://x.test/{next(_URLS)}",
        "score": 0,
        "status": "archived",
        "score_notes": UNTOUCHED_NOTES,
    }
    return Job.create(company=company, title=title, **{**defaults, **fields})


def rows() -> list[tuple]:
    columns = [Job.title, Job.score, Job.score_notes, Job.caveats, Job.salary_min]
    columns += [Job.salary_max, Job.salary_currency, Job.salary_source, Job.status]
    return [tuple(row) for row in Job.select(*columns).order_by(Job.id).tuples()]


def run_main(monkeypatch, *flags, outcomes=None, config=CONFIG, suspend=True) -> Evaluator:
    """Runs main() with the given flags; a title missing from outcomes scores 1.0."""
    evaluator = Evaluator(outcomes or {}, suspend=suspend)
    monkeypatch.setattr(sys, "argv", ["reevaluate_bug_victims.py", *flags])
    monkeypatch.setattr(reevaluate_bug_victims, "load_config", lambda: config)
    with patch.object(reevaluate_bug_victims, "evaluate_job", evaluator):
        reevaluate_bug_victims.main()
    return evaluator


def labeller(total: int) -> Callable[[int, str, str], str]:
    """The progress label every job prints: position of total, company, title padded to 55."""

    def label(position: int, company: str, title: str) -> str:
        return f"[{position:4d}/{total}] [{company}] {title:55s}"

    return label
