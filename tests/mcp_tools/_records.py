"""Rows and canned results the tool tests build their scenes from."""

from unittest.mock import AsyncMock, MagicMock

from moonlighter.core.db import Application, Job
from moonlighter.discovery.evaluation.models import EvaluationResult


def create_job(temporary_database, **overrides):
    """Helper: creates a job in the temp DB. Call init_db() first."""
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "score": 8.0,
        "status": "new",
    }
    defaults.update(overrides)
    return Job.create(**defaults)


def create_application(job, **overrides):
    defaults = {"status": "draft", "form_data": '{"Q": "A"}'}
    defaults.update(overrides)
    return Application.create(job=job, **defaults)


def make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/1"):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock()
    return page


def make_eval_result(score=8.0):
    return EvaluationResult(
        score=score,
        score_notes="Good match.",
        caveats=[],
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="llm_estimate",
    )


def batch_of(result):
    """Mock of evaluate_jobs_batch that returns [result] for each job in the batch."""

    async def _batch(jobs, profile, model, *, caller):
        return [result for _ in jobs]

    return _batch
