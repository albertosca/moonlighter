import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.db import Application, Job, ScanLog, init_db
from moonlighter.core.metrics import record_call
from moonlighter.discovery.evaluator import EvaluationResult

from tests._context import make_test_context

# ── helpers ───────────────────────────────────────────────────────────────────


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


def _batch_of(result):
    """Mock of evaluate_jobs_batch that returns [result] for each job in the batch."""

    async def _batch(jobs, profile, model, caller):
        return [result for _ in jobs]

    return _batch


def create_job(tmp_db, **kwargs):
    """Helper: creates a job in the temp DB. Call init_db() first."""
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "score": 8.0,
        "status": "new",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


def create_application(job, **kwargs):
    defaults = {"status": "draft", "form_data": '{"Q": "A"}'}
    defaults.update(kwargs)
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


# ── scan_and_evaluate ─────────────────────────────────────────────────────────


async def test_scan_no_new_jobs(tmp_db):
    init_db()
    from moonlighter.server import scan_and_evaluate

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for M in (MockGH, MockLV, MockAB):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            M.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())
    assert "No new jobs found" in result


async def test_scan_and_evaluate_reports_archived_stale_jobs(tmp_db):
    init_db()
    from moonlighter.server import scan_and_evaluate

    # Pre-existing eligible job whose company listing will come back empty → stale.
    create_job(
        tmp_db, url="https://boards.greenhouse.io/stale-co/jobs/1", company="stale-co", status="new"
    )

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for M in (MockGH, MockLV, MockAB):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            M.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())

    assert "archived" in result.lower()
    job = Job.get(Job.url == "https://boards.greenhouse.io/stale-co/jobs/1")
    assert job.status == "closed"
    assert job.closed_at is not None


async def test_scan_and_evaluate_no_new_jobs_still_runs_archive_check(tmp_db):
    """Regression: the 'no new jobs' early-exit message must still show the archive section."""
    init_db()
    from moonlighter.server import scan_and_evaluate

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
    ):
        for M in (MockGH, MockLV, MockAB):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            M.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())

    assert "No new jobs found" in result
    assert "No closed jobs found." in result


async def test_scan_all_below_threshold(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse", company="co", title="Eng", url="https://x.com/1", description="desc"
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(make_eval_result(score=4.0)),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())
    assert "threshold" in result.lower()
    # Job should be archived because score=4.0 is below the default threshold=6.5
    job = Job.get(Job.url == "https://x.com/1")
    assert job.status == "archived"


async def test_scan_above_threshold_shows_table(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Sr Eng",
        url="https://x.com/2",
        description="desc",
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(make_eval_result(score=8.0)),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list",
            return_value={"greenhouse": ["stripe"]},
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())
    assert "Stripe" in result
    assert "Sr Eng" in result


async def test_scan_dedup_against_scan_log(tmp_db):
    init_db()
    ScanLog.create(job_url="https://x.com/3", source="greenhouse")
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/3")
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch") as mock_batch,
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(ctx=make_test_context())
    # evaluate_jobs_batch is genuinely not called: the scanner returned the job but
    # dedup (a pre-existing ScanLog) filtered it before it reached _evaluate_and_store.
    mock_batch.assert_not_called()
    assert "No new jobs found" in result


async def test_scan_linkedin_failure_doesnt_block(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse", company="co", title="Eng", url="https://x.com/4", description="desc"
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(make_eval_result(score=8.0)),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("LinkedIn not available"))
        result = await scan_and_evaluate(ctx=make_test_context())
    # LinkedIn failure doesn't block the HTTP results; job with score=8.0 above the threshold.
    assert "co" in result or "Eng" in result or "jobs" in result.lower()


async def test_scan_saves_salary_fields(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com/5",
        description="desc",
    )
    eval_result = EvaluationResult(
        score=8.0,
        score_notes="ok",
        caveats=[],
        salary_min=180000,
        salary_max=220000,
        salary_currency="USD",
        salary_source="stated",
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(eval_result),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list",
            return_value={"greenhouse": ["stripe"]},
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())
    job = Job.get(Job.url == "https://x.com/5")
    assert job.salary_min == 180000
    assert job.salary_currency == "USD"
    assert job.salary_source == "stated"


async def test_scan_saves_caveats_as_json(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse", company="co", title="Eng", url="https://x.com/6", description="desc"
    )
    eval_result = EvaluationResult(
        score=7.0, score_notes="ok", caveats=["US only", "requires visa"]
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(eval_result),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())
    job = Job.get(Job.url == "https://x.com/6")
    caveats = json.loads(job.caveats)
    assert "US only" in caveats
    assert "requires visa" in caveats


async def test_scan_status_archived_if_below_threshold(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse", company="co", title="Eng", url="https://x.com/7", description="desc"
    )
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(make_eval_result(score=3.0)),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())
    # score=3.0 injetado via evaluate_jobs_batch → status genuinamente "archived"
    job = Job.get(Job.url == "https://x.com/7")
    assert job.status == "archived"


# ── scan_company ─────────────────────────────────────────────────────────────


async def test_scan_company_tool_delegates_to_service(tmp_db):
    init_db()
    from moonlighter.server import scan_company

    with patch(
        "moonlighter.discovery.service.scan_company", new=AsyncMock(return_value="report")
    ) as mock_scan_company:
        result = await scan_company("greenhouse", "stripe", ctx=make_test_context())
    assert result == "report"
    mock_scan_company.assert_awaited_once()
    args = mock_scan_company.await_args.args
    assert args[0] == "greenhouse"
    assert args[1] == "stripe"


# ── list_jobs ─────────────────────────────────────────────────────────────────


async def test_list_jobs_default_new(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj1", status="new", score=8.0)
    from moonlighter.server import list_jobs

    result = await list_jobs(status="new", ctx=make_test_context())
    assert "Stripe" in result


async def test_list_jobs_filtered_by_status(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj2", status="reviewed", score=7.0, company="Linear")
    create_job(tmp_db, url="https://x.com/lj3", status="new", score=8.0, company="Vercel")
    from moonlighter.server import list_jobs

    result = await list_jobs(status="reviewed", ctx=make_test_context())
    assert "Linear" in result
    assert "Vercel" not in result


async def test_list_jobs_limit(tmp_db):
    init_db()
    for i in range(5):
        create_job(
            tmp_db,
            url=f"https://x.com/lj-limit-{i}",
            status="new",
            score=float(i),
            company=f"Co{i}",
        )
    from moonlighter.server import list_jobs

    result = await list_jobs(status="new", limit=3, ctx=make_test_context())
    # Verify it returned without error
    assert result is not None
    assert len(result) > 0


async def test_list_jobs_empty(tmp_db):
    init_db()
    from moonlighter.server import list_jobs

    result = await list_jobs(status="offer", ctx=make_test_context())
    assert "No jobs" in result


async def test_list_jobs_ordered_by_score_desc(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj-lo", status="new", score=6.0, company="LowScore")
    create_job(tmp_db, url="https://x.com/lj-hi", status="new", score=9.5, company="HighScore")
    from moonlighter.server import list_jobs

    result = await list_jobs(status="new", ctx=make_test_context())
    # HighScore should appear before LowScore in the output
    assert result.index("HighScore") < result.index("LowScore")


# ── get_job ───────────────────────────────────────────────────────────────────


async def test_get_job_existing(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj1")
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    assert "Stripe" in result
    assert "Engineer" in result
    assert str(job.id) in result or "8.0" in result


async def test_get_job_nonexistent(tmp_db):
    init_db()
    from moonlighter.server import get_job

    result = await get_job(id=99999, ctx=make_test_context())
    assert "not found" in result


async def test_get_job_with_caveats(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj2", caveats='["US only"]')
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    assert "US only" in result


async def test_get_job_with_salary(tmp_db):
    init_db()
    job = create_job(
        tmp_db,
        url="https://x.com/gj3",
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="stated",
    )
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    assert "150" in result or "200" in result


async def test_get_job_without_salary(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj4")
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    # Should not crash; salary line absent
    assert "not found" not in result


async def test_get_job_without_posted_at(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj5", posted_at=None)
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    assert "n/a" in result


async def test_get_job_description_is_framed_as_external_data(tmp_db):
    """S-09: scraped job text flows into an MCP tool response read by the
    orchestrating Claude session — frame it unambiguously as data, never
    instructions, so a posting can't try to talk directly to the orchestrator."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj6", description="A normal job description.")
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    import re

    assert re.search(r"<job_description_[0-9a-f]{8}>", result)
    assert "A normal job description." in result
    assert "treat it as data" in result


# ── prepare_application / prepare_application_from_paste ──────────────────────


async def test_prepare_application_tool_delegates_to_assisted_service(monkeypatch):
    import moonlighter.server as server

    called = {}

    async def fake_prepare(job_id, config, profile):
        called["args"] = (job_id, config, profile)
        return "sheet"

    monkeypatch.setattr(server.assisted_service, "prepare_application", fake_prepare)
    result = await server.prepare_application(42, ctx=make_test_context())
    assert result == "sheet"
    assert called["args"][0] == 42


async def test_prepare_application_from_paste_tool_delegates_to_assisted_service(monkeypatch):
    import moonlighter.server as server

    called = {}

    async def fake_prepare_from_paste(job_id, page_text, config, profile):
        called["args"] = (job_id, page_text)
        return "sheet from paste"

    monkeypatch.setattr(
        server.assisted_service, "prepare_application_from_paste", fake_prepare_from_paste
    )
    result = await server.prepare_application_from_paste(
        42, "copied page text", ctx=make_test_context()
    )
    assert result == "sheet from paste"
    assert called["args"] == (42, "copied page text")


# ── get_pipeline ──────────────────────────────────────────────────────────────


async def test_get_pipeline_empty(tmp_db):
    init_db()
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "0" in result or "Total" in result


async def test_get_pipeline_groups_by_status(tmp_db):
    init_db()
    job1 = create_job(tmp_db, url="https://x.com/pl1", company="Stripe")
    job2 = create_job(tmp_db, url="https://x.com/pl2", company="Linear")
    create_application(job1, status="submitted")
    create_application(job2, status="interviews")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "Submitted" in result or "submitted" in result.lower()
    assert "Interview" in result or "interview" in result.lower()


async def test_get_pipeline_shows_next_action(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl3")
    create_application(job, status="submitted", next_action="follow up em 2026-06-01")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "follow up" in result


async def test_get_pipeline_skips_empty_statuses(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl4")
    create_application(job, status="submitted")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    # "Offer" section should not appear since no offer apps
    assert "## Offer" not in result


async def test_get_pipeline_shows_warnings_when_setup_incomplete(tmp_db):
    """An empty profile (the make_test_context default) surfaces a Setup Warnings
    section with a distinguishable marker, prepended before the pipeline itself."""
    init_db()
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context(profile={}))
    assert "# Setup Warnings" in result
    assert "[WARN]" in result or "[ERROR]" in result
    assert result.index("# Setup Warnings") < result.index("# Application Pipeline")


async def test_get_pipeline_no_warnings_section_when_setup_is_clean(tmp_db, tmp_path):
    """A fully-configured setup (real profile, real cv.pdf, cli backend, existing
    browser) produces zero warnings -> no Setup Warnings section at all, and the
    pipeline output is unchanged from the pre-existing behavior."""
    init_db()
    from moonlighter.server import get_pipeline

    cv = tmp_path / "cv.pdf"
    cv.write_text("fake cv")
    browser = tmp_path / "browser"
    browser.write_text("fake browser")
    config = {"llm_backend": "cli", "browser_path": str(browser)}
    profile = {"skills": ["python"]}

    # `claude` must be pinned as present: the cli backend now checks for it, and
    # the dev machine has it while CI does not -- otherwise this passes locally
    # and fails in CI for a reason that has nothing to do with the assertion.
    with (
        patch("moonlighter.startup.moonlighter_home", return_value=tmp_path),
        patch("moonlighter.startup.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        result = await get_pipeline(ctx=make_test_context(config=config, profile=profile))
    assert "# Setup Warnings" not in result
    assert result.startswith("# Application Pipeline")


async def test_get_pipeline_warnings_distinguish_error_and_warn_levels(tmp_db, tmp_path):
    """No ANTHROPIC_API_KEY + api backend -> an 'error'-level warning; missing cv.pdf
    -> a 'warn'-level warning. Both render with their own marker in the same call."""
    init_db()
    from moonlighter.server import get_pipeline

    with (
        patch("moonlighter.startup.moonlighter_home", return_value=tmp_path),
        patch.dict("os.environ", {}, clear=False),
    ):
        import os as _os

        _os.environ.pop("ANTHROPIC_API_KEY", None)
        config = {"llm_backend": "api"}
        result = await get_pipeline(ctx=make_test_context(config=config, profile={"skills": []}))
    assert "[ERROR]" in result
    assert "[WARN]" in result


# ── update_status ─────────────────────────────────────────────────────────────


async def test_update_status_success(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us1")
    create_application(job)
    from moonlighter.server import update_status

    result = await update_status(job_id=job.id, status="screening", ctx=make_test_context())
    app = Application.get(Application.job == job)
    assert app.status == "screening"
    assert "screening" in result


async def test_update_status_with_notes(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us2")
    create_application(job)
    from moonlighter.server import update_status

    await update_status(
        job_id=job.id,
        status="interviews",
        notes="Scheduled for Monday",
        ctx=make_test_context(),
    )
    app = Application.get(Application.job == job)
    assert "Scheduled for Monday" in app.notes


async def test_update_status_with_next_action(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us3")
    create_application(job)
    from moonlighter.server import update_status

    result = await update_status(
        job_id=job.id, status="screening", next_action="Call Friday", ctx=make_test_context()
    )
    app = Application.get(Application.job == job)
    assert app.next_action == "Call Friday"
    assert "Call Friday" in result


async def test_update_status_invalid(tmp_db):
    init_db()
    from moonlighter.server import update_status

    result = await update_status(job_id=1, status="banana", ctx=make_test_context())
    assert "Invalid" in result or "Status" in result


async def test_update_status_job_not_found(tmp_db):
    init_db()
    from moonlighter.server import update_status

    result = await update_status(job_id=77777, status="screening", ctx=make_test_context())
    assert "not found" in result


async def test_update_status_no_application(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us5")
    # No application
    from moonlighter.server import update_status

    result = await update_status(job_id=job.id, status="screening", ctx=make_test_context())
    assert "application" in result or "not found" in result


async def test_update_status_invalid_leaves_db_untouched(tmp_db):
    """An invalid status must be rejected before any DB write — no partial mutation."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us6")
    create_application(job, status="draft", notes="original notes")
    from moonlighter.server import update_status

    result = await update_status(
        job_id=job.id, status="banana", notes="should not stick", ctx=make_test_context()
    )
    app = Application.get(Application.job == job)
    assert app.status == "draft"
    assert app.notes == "original notes"
    assert "Invalid" in result


@pytest.mark.parametrize(
    "status",
    ["screening", "interviews", "offer", "rejected", "submitted", "draft"],
)
async def test_update_status_accepts_every_valid_status(tmp_db, status):
    """Every documented status value in the `valid` set is actually accepted."""
    init_db()
    job = create_job(tmp_db, url=f"https://x.com/us-valid-{status}")
    create_application(job)
    from moonlighter.server import update_status

    result = await update_status(job_id=job.id, status=status, ctx=make_test_context())
    app = Application.get(Application.job == job)
    assert app.status == status
    assert status in result


async def test_update_status_invalid_lists_accepted_values_sorted(tmp_db):
    """Error message enumerates the accepted statuses, alphabetically sorted."""
    init_db()
    from moonlighter.server import update_status

    result = await update_status(job_id=1, status="not-a-real-status", ctx=make_test_context())
    expected_order = ", ".join(
        sorted({"screening", "interviews", "offer", "rejected", "submitted", "draft"})
    )
    assert expected_order in result


async def test_update_status_appends_multiple_notes_instead_of_overwriting(tmp_db):
    """Calling update_status twice with notes appends, it does not clobber history."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us7")
    create_application(job)
    from moonlighter.server import update_status

    await update_status(
        job_id=job.id, status="screening", notes="First note", ctx=make_test_context()
    )
    await update_status(
        job_id=job.id, status="interviews", notes="Second note", ctx=make_test_context()
    )
    app = Application.get(Application.job == job)
    assert "First note" in app.notes
    assert "Second note" in app.notes
    # Second note comes after the first in the accumulated history.
    assert app.notes.index("First note") < app.notes.index("Second note")


async def test_update_status_without_notes_preserves_existing_notes(tmp_db):
    """Omitting `notes` on a later call must not erase previously stored notes."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us8")
    create_application(job)
    from moonlighter.server import update_status

    await update_status(job_id=job.id, status="screening", notes="Keep me", ctx=make_test_context())
    await update_status(job_id=job.id, status="interviews", ctx=make_test_context())
    app = Application.get(Application.job == job)
    assert "Keep me" in app.notes


async def test_update_status_without_next_action_preserves_existing_value(tmp_db):
    """Omitting `next_action` must not clear a previously set one."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us9")
    create_application(job, next_action="original follow-up")
    from moonlighter.server import update_status

    result = await update_status(job_id=job.id, status="screening", ctx=make_test_context())
    app = Application.get(Application.job == job)
    assert app.next_action == "original follow-up"
    assert "Next action" not in result


async def test_update_status_job_not_found_does_not_leak_other_jobs(tmp_db):
    """A missing job_id returns the not-found message without touching unrelated rows."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us10")
    create_application(job, status="draft")
    from moonlighter.server import update_status

    result = await update_status(job_id=999999, status="offer", ctx=make_test_context())
    assert "not found" in result
    app = Application.get(Application.job == job)
    assert app.status == "draft"  # untouched


async def test_update_status_updates_updated_at_timestamp(tmp_db):
    """updated_at must move forward on a successful status change."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/us11")
    app = create_application(job)
    original_updated_at = app.updated_at
    from moonlighter.server import update_status

    await update_status(job_id=job.id, status="screening", ctx=make_test_context())
    refreshed = Application.get(Application.job == job)
    assert refreshed.updated_at >= original_updated_at


# ── scan_and_evaluate: batch processing ───────────────────────────────────────


async def test_scan_concurrent_batch_all_processed(tmp_db):
    """15 jobs → 3 chunks of 5 (scan_batch_size=5) → evaluate_jobs_batch called 3× → all 15 in DB."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{i}",
            title="Eng",
            url=f"https://x.com/batch/{i}",
            description="desc",
        )
        for i in range(15)
    ]
    mock_batch = AsyncMock(side_effect=_batch_of(make_eval_result(score=7.0)))
    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())
    # chunking assertion: 15 jobs / batch_size=5 → exactly 3 calls to evaluate_jobs_batch
    assert mock_batch.call_count == 3, (
        f"expected 3 chunks, but evaluate_jobs_batch was called {mock_batch.call_count}x "
        f"(chunking loop broken?)"
    )
    assert Job.select().count() == 15


async def test_scan_spend_limit_midbatch_leaves_no_orphan_claims(tmp_db):
    """INVARIANT: when a spend limit is hit inside a chunk, no ScanLog may be left
    without a matching Job (otherwise the job disappears from the pipeline forever).

    Uses scan_batch_size=4 with 8 jobs (2 chunks of 4) and scan_concurrency=1
    to serialize: chunk 0 calls evaluate_jobs_batch (which raises spend-limit),
    the `for raw in to_eval: _release(raw)` loop runs for the chunk's 4 jobs,
    and chunk 1 sees the stop event and touches nothing else.

    This test FAILS if the _release loop is removed from the spend-limit except
    clause: without release, chunk 0's 4 jobs end up with a ScanLog but no Job."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{i}",
            title="Eng",
            url=f"https://x.com/orphan/{i}",
            description="desc",
        )
        for i in range(8)
    ]

    spend_limit_err = Exception("You've hit your monthly spend limit")
    mock_batch = AsyncMock(side_effect=spend_limit_err)

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(
            ctx=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 4,
                }
            )
        )

    job_urls = {j.url for j in Job.select()}
    orphans = [sl.job_url for sl in ScanLog.select() if sl.job_url not in job_urls]
    assert orphans == [], f"orphan claims (claim without Job): {orphans}"


async def test_scan_spend_limit_stops_further_batches(tmp_db):
    """When batch 1 hits the spend limit, the following batches are not attempted.

    With scan_concurrency=1 the chunks are serialized: chunk 0 calls
    evaluate_jobs_batch (which raises spend-limit), sets the stop event, and
    releases the semaphore; chunks 1 and 2 see the stop before calling
    evaluate_jobs_batch. Concrete proof of early stop: call_count == 1, not 3."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{i}",
            title="Eng",
            url=f"https://x.com/stop/{i}",
            description="desc",
        )
        for i in range(15)  # 3 batches of 5 with scan_batch_size=5
    ]

    spend_limit_err = Exception("usage limit reached")
    mock_batch = AsyncMock(side_effect=spend_limit_err)

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(
            ctx=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 5,
                }
            )
        )

    # With scan_concurrency=1 the stop prevents batches 2 and 3 from calling the LLM.
    # call_count should be 1 (not 3 = total batches).
    assert mock_batch.call_count == 1, (
        f"expected 1 call to evaluate_jobs_batch, but there were {mock_batch.call_count} "
        f"(batches 2 and 3 should have been stopped by the stop event)"
    )
    # and no orphan claim remained
    job_urls = {j.url for j in Job.select()}
    assert all(sl.job_url in job_urls for sl in ScanLog.select())


async def test_scan_non_spend_error_keeps_title_filtered_in_report(tmp_db):
    """A generic (non-spend-limit) error in evaluate_jobs_batch must not drop the
    title-filtered jobs already persisted earlier in the same chunk from the report
    count — they're already saved in the DB, the report must reflect that too."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Staff Accountant",
            url="https://x.com/nonspend/1",
            description="desc",
        ),
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/nonspend/2",
            description="desc",
        ),
    ]
    mock_batch = AsyncMock(side_effect=Exception("unexpected LLM error"))

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=mock_batch),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(
            ctx=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": ["staff accountant"],
                    "scan_concurrency": 1,
                    "scan_batch_size": 2,
                }
            )
        )

    # Already true today: the title-filtered job is persisted regardless of the bug.
    filtered_job = Job.get(Job.url == "https://x.com/nonspend/1")
    assert filtered_job.status == "archived"
    # The bug: the report text undercounts it as 0 instead of 1.
    assert "1 filtered by title" in result, (
        f"expected the title-filtered job to be counted in the report even with a "
        f"non-spend-limit error in the batch; report: {result!r}"
    )


async def test_scan_chunk_crash_outside_try_except_does_not_break_whole_scan(tmp_db):
    """A bug that crashes evaluate_chunk itself (outside its own try/except, e.g. a
    _persist failure) must not blow up the whole scan_and_evaluate call — gather's
    return_exceptions=True catches it, this chunk contributes nothing, other chunks
    are unaffected."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/crash/1",
            description="desc",
        ),
    ]

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service._claim", side_effect=Exception("db corrupted")),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate(
            ctx=make_test_context(
                config={
                    "score_threshold": 6.5,
                    "llm_model": "claude-haiku-4-5-20251001",
                    "title_blocklist": [],
                    "scan_concurrency": 1,
                    "scan_batch_size": 5,
                }
            )
        )  # must not raise

    assert Job.select().count() == 0
    assert "0 jobs processed" in result


async def test_get_pipeline_shows_needs_review(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl-nr", company="Stripe")
    create_application(job, status="needs_review")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "needs_review" in result.lower()


# ── get_job: bug fix verification ─────────────────────────────────────────────


async def test_get_job_score_null(tmp_db):
    """get_job with score=None must not raise TypeError (bug fix)."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj-null-score", score=None)
    from moonlighter.server import get_job

    result = await get_job(id=job.id, ctx=make_test_context())
    assert "—" in result
    assert "not found" not in result


# ── list_jobs: table formatting ───────────────────────────────────────────────


async def test_list_jobs_salary_estimate_shows_asterisk(tmp_db):
    """salary_source='llm_estimate' with min+max → '* ' appears in table."""
    init_db()
    create_job(
        tmp_db,
        url="https://x.com/lj-est",
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="llm_estimate",
        status="new",
    )
    from moonlighter.server import list_jobs

    result = await list_jobs(status="new", ctx=make_test_context())
    assert " *" in result


async def test_list_jobs_salary_min_only_shows_plus(tmp_db):
    """Only salary_min set → '$Xk+' format in table."""
    init_db()
    create_job(
        tmp_db,
        url="https://x.com/lj-min",
        salary_min=120000,
        salary_max=None,
        salary_currency="USD",
        salary_source="stated",
        status="new",
    )
    from moonlighter.server import list_jobs

    result = await list_jobs(status="new", ctx=make_test_context())
    assert "k+" in result or "120" in result


# ── get_pipeline: total count ─────────────────────────────────────────────────


async def test_get_pipeline_total_count(tmp_db):
    """Total de candidaturas count reflects all Applications regardless of status."""
    init_db()
    job1 = create_job(tmp_db, url="https://x.com/pl-tc1")
    job2 = create_job(tmp_db, url="https://x.com/pl-tc2")
    job3 = create_job(tmp_db, url="https://x.com/pl-tc3")
    create_application(job1, status="submitted")
    create_application(job2, status="interviews")
    create_application(job3, status="rejected")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "3" in result


async def test_get_pipeline_every_status_bucket_appears(tmp_db):
    """One application per status: every bucket header shows up, in the tool's declared order."""
    init_db()
    statuses = [
        "draft",
        "needs_review",
        "submitted",
        "screening",
        "interviews",
        "offer",
        "rejected",
    ]
    for i, status in enumerate(statuses):
        job = create_job(tmp_db, url=f"https://x.com/pl-all-{i}", company=f"Co{i}")
        create_application(job, status=status)
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    headers = [f"## {status.capitalize()} (1)" for status in statuses]
    positions = [result.index(header) for header in headers]
    # Headers appear in the declared status order, not e.g. insertion order.
    assert positions == sorted(positions)
    assert "**Total applications:** 7" in result


async def test_get_pipeline_multiple_applications_same_status_ordered_by_updated_at_desc(tmp_db):
    """Within a bucket, applications are ordered most-recently-updated first."""
    init_db()
    job_old = create_job(tmp_db, url="https://x.com/pl-ord1", company="OldCo")
    job_new = create_job(tmp_db, url="https://x.com/pl-ord2", company="NewCo")
    create_application(job_old, status="submitted")
    create_application(job_new, status="submitted")
    # Force NewCo's application to have a strictly later updated_at.
    from datetime import timedelta

    app_new = Application.get(Application.job == job_new)
    app_new.updated_at = app_new.updated_at + timedelta(days=1)
    app_new.save()
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert result.index("NewCo") < result.index("OldCo")


async def test_get_pipeline_no_applied_at_shows_dash(tmp_db):
    """An application without applied_at renders '—' instead of a date/crashing."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl-noapplied")
    create_application(job, status="draft", applied_at=None)
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "(—)" in result


async def test_get_pipeline_shows_job_company_and_title(tmp_db):
    """Each pipeline row includes the job's id, company and title."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl-fmt", company="Acme Corp", title="Backend Dev")
    create_application(job, status="submitted")
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert f"#{job.id} Acme Corp/Backend Dev" in result


async def test_get_pipeline_empty_has_zero_total_and_no_bucket_headers(tmp_db):
    """With zero applications, no '## Status' header appears anywhere, and total is 0."""
    init_db()
    from moonlighter.server import get_pipeline

    result = await get_pipeline(ctx=make_test_context())
    assert "## " not in result
    assert "**Total applications:** 0" in result


# ── validate_startup integration ──────────────────────────────────────────────


def test_validate_startup_called_at_import_with_real_config():
    """validate_startup does not raise an exception during mcp_server startup."""
    # mcp_server was already imported in previous tests.
    # This test ensures the module imports without crashing even without an API key.
    import moonlighter.server  # noqa: F401 — verifies it imports ok

    assert True  # if we got here, it didn't crash


def test_startup_warning_level_values():
    from moonlighter.startup import StartupWarning

    w_err = StartupWarning(level="error", message="msg")
    w_warn = StartupWarning(level="warn", message="msg")
    assert w_err.level == "error"
    assert w_warn.level == "warn"


# ── Registered browser-scanner plugin: session expired warning ────────────────
# LinkedIn is the real-world example of a "moonlighter.scanners" entry_points
# plugin (see docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md),
# provided by the private moonlighter-linkedin package, not by this repo. These
# tests prove the generic dispatch/warning mechanism with a fake scanner instead.


class _FakeSessionExpiredSource:
    def __init__(self, page: Any) -> None:
        pass

    async def scan(self, **kwargs: Any) -> list[Any]:
        from moonlighter.discovery.sources.base import ScannerSessionExpiredError

        raise ScannerSessionExpiredError("Session expired.")


async def test_scan_registered_scanner_session_expired_shows_warning(tmp_db):
    """A registered browser-scanner plugin raising ScannerSessionExpiredError ->
    explicit warning in the result (no silence)."""
    init_db()
    from moonlighter.server import scan_and_evaluate

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.discover_entry_points",
            return_value=[_FakeSessionExpiredSource],
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        result = await scan_and_evaluate(ctx=make_test_context())

    assert "⚠️  _FakeSessionExpiredSource: Session expired." in result
    assert "expired" in result or "login" in result.lower()


async def test_scan_registered_scanner_session_expired_does_not_block_http_results(tmp_db):
    """A registered browser-scanner plugin's ScannerSessionExpiredError does not
    prevent HTTP jobs from being returned."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com/li-exp-1",
        description="desc",
    )

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch(
            "moonlighter.discovery.service.discover_entry_points",
            return_value=[_FakeSessionExpiredSource],
        ),
        patch(
            "moonlighter.discovery.service.evaluate_jobs_batch",
            new=_batch_of(make_eval_result(score=8.0)),
        ),
        patch(
            "moonlighter.discovery.service.load_company_list",
            return_value={"greenhouse": ["stripe"]},
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        result = await scan_and_evaluate(ctx=make_test_context())

    assert "Stripe" in result  # HTTP job appears
    assert "_FakeSessionExpiredSource" in result  # warning appears too


# ── email: setup_email MCP tool ───────────────────────────────────────────────


async def test_setup_email_calls_gmail_flow():
    """setup_email should start the OAuth flow and confirm success."""
    from moonlighter.server import setup_email

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
        }
    }
    with (
        patch("moonlighter.server.setup_gmail_service") as mock_setup,
        patch("moonlighter.server._run_gmail_oauth") as mock_oauth,
        patch("os.path.exists", return_value=True),
    ):
        mock_oauth.return_value = None
        mock_setup.return_value = MagicMock()
        result = await setup_email(ctx=make_test_context(config=test_config))

    assert "success" in result.lower() or "configured" in result.lower()


async def test_setup_email_raises_friendly_error_when_client_json_missing():
    """setup_email should return a clear message if gmail-client.json does not exist."""
    from moonlighter.server import setup_email

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "/nonexistent/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
        }
    }
    result = await setup_email(ctx=make_test_context(config=test_config))

    assert "client" in result.lower() or "credential" in result.lower() or "error" in result.lower()


# ── email: sync_email_responses MCP tool ─────────────────────────────────────


async def test_sync_email_responses_returns_summary(tmp_db):
    """sync_email_responses should call sync_responses and return a readable summary."""
    init_db()
    from moonlighter.server import sync_email_responses

    fake_updates = [
        {
            "company": "Anthropic",
            "title": "Senior Engineer",
            "type": "interview",
            "stage": "technical_interview",
            "match_type": "ref",
        },
        {
            "company": "Stripe",
            "title": "Backend Eng",
            "type": "rejection",
            "stage": None,
            "match_type": "fuzzy",
        },
    ]
    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
            "processed_label": "moonlighter/processed",
            "interview_stages": [],
        },
        "llm_model": "claude-sonnet-4-6",
    }

    with patch("moonlighter.server.sync_responses", new=AsyncMock(return_value=fake_updates)):
        result = await sync_email_responses(ctx=make_test_context(config=test_config))

    assert "Anthropic" in result
    assert "Stripe" in result
    assert "2" in result or len(result) > 10


async def test_sync_email_responses_empty_inbox(tmp_db):
    """sync_email_responses with an empty inbox should return an appropriate message."""
    init_db()
    from moonlighter.server import sync_email_responses

    test_config = {
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "~/.moonlighter/gmail-client.json",
            "token_path": "~/.moonlighter/gmail-token.json",
            "processed_label": "moonlighter/processed",
            "interview_stages": [],
        },
        "llm_model": "claude-sonnet-4-6",
    }

    with patch("moonlighter.server.sync_responses", new=AsyncMock(return_value=[])):
        result = await sync_email_responses(ctx=make_test_context(config=test_config))

    assert "no new" in result.lower() or "0" in result


async def test_sync_email_responses_flags_fuzzy_match_as_suggestion(tmp_db):
    """S-06: the sync_email_responses report must tell the human a fuzzy match
    was NOT applied and needs manual update_status confirmation."""
    init_db()
    from moonlighter.server import sync_email_responses

    with patch(
        "moonlighter.server.sync_responses",
        new=AsyncMock(
            return_value=[
                {
                    "company": "Stripe",
                    "title": "Backend Engineer",
                    "type": "interview",
                    "stage": "technical_interview",
                    "match_type": "fuzzy",
                    "summary": "x",
                    "suggested_job_id": 42,
                    "needs_confirmation": True,
                }
            ]
        ),
    ):
        result = await sync_email_responses(ctx=make_test_context())

    assert "update_status" in result
    assert "42" in result
    assert "⚠️" in result


def test_mcp_server_initializes_logging():
    """Importing mcp_server must not blow up and must have logging set up."""
    import moonlighter.core.log as log_mod

    # if the module was already imported, _initialized should be True
    assert log_mod._initialized is True


# ── scan race condition (duplicate LLM calls) ─────────────────────────────────


def _scan_patches(raw_jobs, eval_mock):
    """Context manager stack shared by race condition tests."""
    from contextlib import ExitStack
    from unittest.mock import AsyncMock, patch

    stack = ExitStack()
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.http.GreenhouseScanner",
            **{"return_value.scan": AsyncMock(return_value=raw_jobs)},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.http.LeverScanner",
            **{"return_value.scan": AsyncMock(return_value=[])},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.discovery.sources.http.AshbyScanner",
            **{"return_value.scan": AsyncMock(return_value=[])},
        )
    )
    stack.enter_context(
        patch(
            "moonlighter.core.browser",
            create=True,
            **{"new_page": AsyncMock(side_effect=Exception("no browser"))},
        )
    )

    async def _batch(jobs, profile, model, caller):
        # Calls eval_mock per job; errors (spend limit) propagate to evaluate_chunk.
        return [
            await eval_mock(j.company, j.title, j.description, profile, model, caller) for j in jobs
        ]

    stack.enter_context(patch("moonlighter.discovery.service.evaluate_jobs_batch", new=_batch))
    stack.enter_context(
        patch(
            "moonlighter.discovery.service.load_company_list",
            return_value={"greenhouse": ["co"]},
        )
    )
    return stack


async def test_scan_concurrent_calls_evaluate_same_url_only_once(tmp_db):
    """Concurrent scan_and_evaluate calls must not call evaluate_job twice for the same URL.

    Reproduces the race condition where 11 parallel MCP tool invocations each saw
    the same empty ScanLog snapshot and fired 11 LLM calls per job.
    """
    import asyncio

    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    url = "https://x.com/race-1"
    raw = RawJob(source="greenhouse", company="Co", title="Eng", url=url, description="desc")
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        # Fire 5 concurrent scans for the same job
        await asyncio.gather(*[scan_and_evaluate(ctx=make_test_context()) for _ in range(5)])

    # LLM must have been called exactly once despite 5 concurrent scans
    assert eval_mock.call_count == 1
    # Exactly one Job and one ScanLog entry
    assert Job.select().where(Job.url == url).count() == 1
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 1


async def test_scan_spend_limit_releases_scan_log_claim(tmp_db):
    """When evaluate_job hits the spend limit, the scan STOPS CLEANLY (does not crash):
    it releases the claim in ScanLog (URL retryable on the next scan), does not create
    a Job, and warns in the return. Conservative contract — no exception propagates to the tool."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    url = "https://x.com/spend-limit-1"
    raw = RawJob(source="greenhouse", company="Co", title="Eng", url=url, description="desc")
    spend_limit_err = Exception(
        "claude CLI exited with code 1: You've hit your monthly spend limit"
    )
    failing_eval = AsyncMock(side_effect=spend_limit_err)

    with _scan_patches([raw], failing_eval):
        result = await scan_and_evaluate(ctx=make_test_context())

    # Does not raise — reports the limit in the return text.
    assert "spend limit" in result.lower() or "interrompido" in result.lower()
    # Claim released — empty ScanLog so the next scan can retry the URL.
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 0
    # Nenhum Job criado.
    assert Job.select().where(Job.url == url).count() == 0


async def test_scan_already_in_scan_log_skips_llm(tmp_db):
    """URL already in ScanLog at scan start → evaluate_job not called (existing dedup)."""
    init_db()
    ScanLog.create(job_url="https://x.com/already-seen", source="greenhouse")
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raw = RawJob(source="greenhouse", company="Co", title="Eng", url="https://x.com/already-seen")
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        await scan_and_evaluate(ctx=make_test_context())

    eval_mock.assert_not_called()


# ── add_job tool wrapper + setup_email error handlers ───────────────────────


async def test_add_job_tool_delegates_to_service(tmp_db):
    """O wrapper MCP add_job delega ao scan_service e devolve o resultado."""
    init_db()
    from moonlighter.server import add_job

    with patch(
        "moonlighter.discovery.service.evaluate_job",
        new=AsyncMock(return_value=make_eval_result(8.0)),
    ):
        result = await add_job(
            url="https://x.com/manual/tool/1",
            company="Stripe",
            title="Eng",
            description="desc",
            ctx=make_test_context(),
        )
    assert "Stripe" in result or "NEW" in result


# ── archive_stale_jobs (MCP tool) ───────────────────────────────────────────


async def test_tool_archive_stale_jobs_delegates_and_formats(tmp_db):
    init_db()
    from moonlighter.discovery.archive import ArchiveResult
    from moonlighter.server import archive_stale_jobs

    fake_result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        failed_companies=["beta"],
    )
    with patch(
        "moonlighter.server.scan_service.archive_stale_jobs",
        new=AsyncMock(return_value=fake_result),
    ):
        result = await archive_stale_jobs(ctx=make_test_context())

    assert "acme" in result
    assert "beta" in result


async def test_tool_archive_stale_jobs_passes_filters(tmp_db):
    init_db()
    from moonlighter.discovery.archive import ArchiveResult
    from moonlighter.server import archive_stale_jobs

    mock_service = AsyncMock(return_value=ArchiveResult())
    with patch("moonlighter.server.scan_service.archive_stale_jobs", new=mock_service):
        await archive_stale_jobs(job_id=123, company=None, ctx=make_test_context())

    mock_service.assert_awaited_once()
    args = mock_service.await_args.args
    assert args[0] == 123
    assert args[1] is None


async def test_tool_archive_stale_jobs_rejects_both_filters(tmp_db):
    init_db()
    from moonlighter.discovery.archive import ArchiveStaleJobsError
    from moonlighter.server import archive_stale_jobs

    with patch(
        "moonlighter.server.scan_service.archive_stale_jobs",
        new=AsyncMock(side_effect=ArchiveStaleJobsError("Provide job_id OR company, not both.")),
    ):
        result = await archive_stale_jobs(job_id=1, company="acme", ctx=make_test_context())

    assert "OR company" in result


async def test_setup_email_handles_auth_error(tmp_path):
    """GmailAuthError during OAuth → friendly message (server.py setup_email)."""
    from moonlighter.server import setup_email
    from moonlighter.tracking.gmail_client import GmailAuthError

    creds = tmp_path / "gmail-client.json"
    creds.write_text("{}")
    test_config = {
        "email": {"credentials_path": str(creds), "token_path": str(tmp_path / "t.json")}
    }
    with patch("moonlighter.server._run_gmail_oauth", side_effect=GmailAuthError("invalid token")):
        result = await setup_email(ctx=make_test_context(config=test_config))
    assert "Gmail" in result and "invalid token" in result


async def test_setup_email_handles_unexpected_error(tmp_path):
    """Unexpected exception during OAuth → unexpected-error message (server.py setup_email)."""
    from moonlighter.server import setup_email

    creds = tmp_path / "gmail-client.json"
    creds.write_text("{}")
    test_config = {
        "email": {"credentials_path": str(creds), "token_path": str(tmp_path / "t.json")}
    }
    with patch("moonlighter.server._run_gmail_oauth", side_effect=RuntimeError("boom")):
        result = await setup_email(ctx=make_test_context(config=test_config))
    assert "unexpected" in result.lower()


# ── observability (Task 4): scan_and_evaluate opens one operation_metrics scope ─


async def test_scan_and_evaluate_logs_one_metrics_summary(tmp_db, caplog):
    """With a stubbed evaluate_jobs_batch that records one LLM call per job (as the
    real evaluator/caller would), scan_and_evaluate must emit exactly one
    `op=scan_and_evaluate` summary line naming the right call count — proof the
    tool wraps its whole body in a single operation_metrics scope, not one
    scope per job/batch (which would split the counts across many lines)."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company=f"Co{i}",
            title="Eng",
            url=f"https://x.com/metrics/{i}",
            description="desc",
        )
        for i in range(3)
    ]

    async def _batch_records_calls(jobs, profile, model, caller):
        result = make_eval_result(score=8.0)
        out = []
        for _ in jobs:
            record_call(0.01, input_tokens=1, output_tokens=2)
            out.append(result)
        return out

    with (
        caplog.at_level(logging.INFO),
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=_batch_records_calls),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())

    summary_lines = [r for r in caplog.records if "op=scan_and_evaluate" in r.getMessage()]
    assert len(summary_lines) == 1
    msg = summary_lines[0].getMessage()
    assert "calls=3" in msg
    assert "spend_limit_hits=0" in msg


async def test_scan_and_evaluate_spend_limit_abort_increments_hits(tmp_db, caplog):
    """A spend-limit abort mid-scan increments spend_limit_hits in the single
    scan_and_evaluate summary (evaluator/service call record_spend_limit_hit()
    before propagating, inside the tool's one operation_metrics scope)."""
    init_db()
    from moonlighter.discovery.sources.base import RawJob
    from moonlighter.server import scan_and_evaluate

    raws = [
        RawJob(
            source="greenhouse",
            company="co",
            title="Eng",
            url="https://x.com/quota/1",
            description="desc",
        )
    ]

    async def _batch_raises_spend_limit(jobs, profile, model, caller):
        # Deliberately does NOT call record_spend_limit_hit() itself — the
        # production `except is_spend_limit(e)` catch site in
        # moonlighter.discovery.service is what must record the hit, exactly
        # once, before propagating.
        raise RuntimeError("spend limit reached")

    with (
        caplog.at_level(logging.INFO),
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.core.browser", create=True) as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=_batch_raises_spend_limit),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate(ctx=make_test_context())

    summary_lines = [r for r in caplog.records if "op=scan_and_evaluate" in r.getMessage()]
    assert len(summary_lines) == 1
    assert "spend_limit_hits=1" in summary_lines[0].getMessage()
