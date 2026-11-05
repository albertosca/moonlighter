"""add_job scores a posting, saves every scored field and words the answer."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery.manual.jobs import add_job

from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result


async def test_add_job_new_above_threshold_with_caveats(temporary_database):
    init_db()
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(9.0, caveats=["visa", "relocation"])),
    ):
        result = await add_job(
            "https://x.com/9", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "NEW" in result
    assert "visa" in result
    assert "relocation" in result
    assert Job.get(Job.url == "https://x.com/9").status == "new"
    assert ScanLog.get(ScanLog.job_url == "https://x.com/9").source == "manual"


async def test_add_job_below_threshold_archived(temporary_database):
    init_db()
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(3.0)),
    ):
        result = await add_job(
            "https://x.com/10", "Acme", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "archived" in result
    assert "none" in result  # no caveats
    assert Job.get(Job.url == "https://x.com/10").status == "archived"


async def test_add_job_integrity_conflict_on_create(temporary_database):
    init_db()
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/11", status="new")
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(8.0)),
    ):
        result = await add_job(
            "https://x.com/11", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


async def test_add_job_result_text_is_pinned_exactly_for_a_new_job(temporary_database):
    init_db()
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(9.0, caveats=["visa", "relocation"])),
    ):
        result = await add_job(
            "https://x.com/pin/1", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    job = Job.get(Job.url == "https://x.com/pin/1")
    assert result == (
        "✓ NEW — Stripe / Eng\n"
        "Score: 9.0/10  (threshold: 7.0)\n"
        "Notes: match\n"
        "Caveats:\n"
        "  ⚠ visa\n"
        "  ⚠ relocation\n"
        f"id={job.id}"
    )


async def test_add_job_result_text_is_pinned_exactly_for_an_archived_job(temporary_database):
    init_db()
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(3.0)),
    ):
        result = await add_job(
            "https://x.com/pin/2", "Acme", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    job = Job.get(Job.url == "https://x.com/pin/2")
    assert result == (
        "archived — Acme / Eng\n"
        "Score: 3.0/10  (threshold: 7.0)\n"
        "Notes: match\n"
        "Caveats:\n"
        "  none\n"
        f"id={job.id}"
    )


async def test_add_job_persists_every_scored_field(temporary_database):
    init_db()
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(9.0, caveats=["visa"])),
    ):
        await add_job("https://x.com/pin/3", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock())
    job = Job.get(Job.url == "https://x.com/pin/3")
    assert job.source == "manual"
    assert job.description == "desc"
    assert job.score == 9.0
    assert job.score_notes == "match"
    assert job.caveats == '["visa"]'
    assert (job.salary_min, job.salary_max) == (150000, 200000)
    assert (job.salary_currency, job.salary_source) == ("USD", "llm_estimate")
    assert job.status == "new"


async def test_add_job_takes_the_model_from_eval_model_then_llm_model_then_the_default(
    temporary_database,
):
    init_db()
    evaluator = AsyncMock(return_value=evaluation_result(8.0))
    models = []
    with patch("moonlighter.discovery.manual.jobs.evaluate_job", new=evaluator):
        for index, extra in enumerate(
            [
                {"eval_model": "from-eval", "llm_model": "from-llm"},
                {"llm_model": "from-llm"},
                {},
            ]
        ):
            config = {"score_threshold": 7.0, **extra}
            await add_job(
                f"https://x.com/pin/m{index}", "Acme", "Eng", "desc", config, PROFILE, MagicMock()
            )
            models.append(evaluator.call_args.kwargs["model"])
    assert models == ["from-eval", "from-llm", "claude-haiku-4-5-20251001"]
