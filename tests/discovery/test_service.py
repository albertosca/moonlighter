"""Tests for scan_service focused on add_job (manual job) and the edge branches
of scan_and_evaluate that test_mcp_server's happy path doesn't cover.

add_job is called directly on the service (not via the MCP tool) to isolate the
config/profile/caller logic, without depending on the global config loaded on import.
"""

import asyncio
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.core.db import Job, ScanLog, init_db
from moonlighter.discovery import service as scan_service
from moonlighter.discovery.evaluator import EvaluationResult

CONFIG = {
    "score_threshold": 7.0,
    "llm_model": "claude-haiku-4-5-20251001",
    "title_blocklist": ["staff accountant"],
}
PROFILE: dict = {}


def _eval(score=8.0, caveats=None):
    return EvaluationResult(
        score=score,
        score_notes="match",
        caveats=caveats or [],
        salary_min=150000,
        salary_max=200000,
        salary_currency="USD",
        salary_source="llm_estimate",
    )


def _http_client(status_code=200, text="<p>Job description here</p>"):
    """Builds a mocked AsyncClient that works as an async context manager."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=status_code, text=text))
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=client)
    acm.__aexit__ = AsyncMock(return_value=False)
    return acm, client


# ── input validation ────────────────────────────────────────────────────────


async def test_add_job_missing_company_title(tmp_db):
    init_db()
    result = await scan_service.add_job(
        "https://x.com/1", "", "", "provided desc", CONFIG, PROFILE, MagicMock()
    )
    assert "company" in result and "title" in result


# ── automatic description lookup via HTTP ───────────────────────────────────


async def test_add_job_fetches_description_when_empty(tmp_db):
    init_db()
    acm, _ = _http_client(text="<html><body>Real desc</body></html>")
    with (
        patch("moonlighter.discovery.service.httpx.AsyncClient", return_value=acm),
        patch(
            "moonlighter.discovery.service.evaluate_job",
            new=AsyncMock(return_value=_eval(8.0)),
        ),
    ):
        result = await scan_service.add_job(
            "https://x.com/2", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "NEW" in result
    job = Job.get(Job.url == "https://x.com/2")
    assert "Real desc" in (job.description or "")


async def test_add_job_http_non_200_returns_error(tmp_db):
    init_db()
    acm, _ = _http_client(status_code=404)
    with patch("moonlighter.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/3", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "404" in result


async def test_add_job_http_exception_returns_error(tmp_db):
    init_db()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    acm.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/4", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "Error fetching URL" in result


# ── deduplication ───────────────────────────────────────────────────────────


async def test_add_job_dedup_existing_job(tmp_db):
    init_db()
    Job.create(
        source="manual",
        company="Stripe",
        title="Eng",
        url="https://x.com/5",
        score=8.0,
        status="new",
    )
    ScanLog.create(job_url="https://x.com/5", source="manual")
    result = await scan_service.add_job(
        "https://x.com/5", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "already in the database" in result


async def test_add_job_scanlog_without_job_proceeds_to_eval(tmp_db):
    init_db()
    # ScanLog has the URL but there's no Job (rare inconsistent state) → dedup lets
    # it through (Job.get raises DoesNotExist), evaluates, but the final ScanLog.create
    # collides with the existing record → IntegrityError → conflict message.
    ScanLog.create(job_url="https://x.com/6", source="manual")
    with patch(
        "moonlighter.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/6", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


# ── title filter ────────────────────────────────────────────────────────────


async def test_add_job_title_blocklist_archives(tmp_db):
    init_db()
    result = await scan_service.add_job(
        "https://x.com/7", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "discarded by the title filter" in result
    job = Job.get(Job.url == "https://x.com/7")
    assert job.status == "archived"
    assert job.score == 0.0


async def test_add_job_title_blocklist_integrity_swallowed(tmp_db):
    init_db()
    # Pre-creates the URL to force IntegrityError in Job.create on the blocklist branch.
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/8", status="new")
    result = await scan_service.add_job(
        "https://x.com/8", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "discarded by the title filter" in result


# ── evaluation and persistence ───────────────────────────────────────────────


async def test_add_job_new_above_threshold_with_caveats(tmp_db):
    init_db()
    with patch(
        "moonlighter.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(9.0, caveats=["visa", "relocation"])),
    ):
        result = await scan_service.add_job(
            "https://x.com/9", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "NEW" in result
    assert "visa" in result and "relocation" in result
    assert Job.get(Job.url == "https://x.com/9").status == "new"
    assert ScanLog.get(ScanLog.job_url == "https://x.com/9").source == "manual"


async def test_add_job_below_threshold_archived(tmp_db):
    init_db()
    with patch(
        "moonlighter.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(3.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/10", "Acme", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "archived" in result
    assert "none" in result  # no caveats
    assert Job.get(Job.url == "https://x.com/10").status == "archived"


async def test_add_job_integrity_conflict_on_create(tmp_db):
    init_db()
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/11", status="new")
    with patch(
        "moonlighter.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/11", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


# ── scan_and_evaluate edge branches ──────────────────────────────────────────

from moonlighter.discovery.sources.base import RawJob  # noqa: E402


def _raw(i, title="Engineer", source="greenhouse"):
    return RawJob(
        source=source,
        company=f"Co{i}",
        title=title,
        url=f"https://x.com/scan/{i}",
        description="desc",
    )


class _FakeBrowserScanner:
    """Stands in for a registered moonlighter.scanners plugin (LinkedIn is the
    real-world example, provided by the private moonlighter-linkedin package --
    see docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md).
    _run_scan configures its scan() return/raise per test via closure."""

    _exc: Exception | None = None
    _jobs: ClassVar[list] = []

    def __init__(self, page):
        pass

    async def scan(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._jobs


async def _run_scan(raws, *, eval_mock=None, linkedin_exc=None, linkedin_jobs=None, config=None):
    """Runs scan_and_evaluate with mocked HTTP scanners serving `raws`.

    linkedin_exc: the exception the registered browser-scanner plugin's scan()
    should raise. linkedin_jobs: the list of RawJob it should return instead.
    If both are None, no browser-scanner plugin is registered at all (the
    steady state for the public repo alone).

    eval_mock: an AsyncMock applied per job within the batch. Can be
    AsyncMock(return_value=EvaluationResult) or AsyncMock(side_effect=exc).
    """
    cfg = config or {**CONFIG, "title_blocklist": ["staff accountant"]}
    _eval_per_job = eval_mock or AsyncMock(return_value=_eval(8.0))

    async def _batch(jobs, profile, model, caller):
        # Applies eval_mock to each job in the batch; errors propagate to evaluate_chunk.
        return [await _eval_per_job(j.company, model) for j in jobs]

    registered = []
    if linkedin_exc is not None or linkedin_jobs is not None:
        _FakeBrowserScanner._exc = linkedin_exc
        _FakeBrowserScanner._jobs = linkedin_jobs or []
        registered = [_FakeBrowserScanner]

    with (
        patch("moonlighter.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("moonlighter.discovery.sources.http.LeverScanner") as MockLV,
        patch("moonlighter.discovery.sources.http.AshbyScanner") as MockAB,
        patch("moonlighter.discovery.service.browser") as mock_browser,
        patch("moonlighter.discovery.service.evaluate_jobs_batch", new=_batch),
        patch("moonlighter.discovery.service.discover_entry_points", return_value=registered),
        patch(
            "moonlighter.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}
        ),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=AsyncMock())
        return await scan_service.scan_and_evaluate("", "all", cfg, PROFILE, MagicMock())


async def test_run_browser_scanner_browser_launch_failure_is_silent():
    """If browser.new_page() itself raises (no browser configured, launch error),
    the browser-scanner plugin is skipped silently -- same as any other failure,
    it must not block the HTTP results."""
    with patch("moonlighter.discovery.service.browser") as mock_browser:
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        jobs, warning = await scan_service._run_browser_scanner(
            _FakeBrowserScanner, "engineer", CONFIG
        )
    assert jobs == []
    assert warning is None


async def test_scan_linkedin_jobs_are_evaluated(tmp_db):
    init_db()
    li_raw = RawJob(
        source="linkedin",
        company="LinkedInCo",
        title="Engineer",
        url="https://x.com/li/1",
        description="desc",
    )
    result = await _run_scan([], linkedin_jobs=[li_raw])
    assert Job.get(Job.url == "https://x.com/li/1").company == "LinkedInCo"
    assert "LinkedInCo" in result


async def test_scan_title_filtered_archives_with_score_zero(tmp_db):
    init_db()
    result = await _run_scan([_raw(1, title="Staff Accountant")])
    job = Job.get(Job.url == "https://x.com/scan/1")
    assert job.status == "archived"
    assert job.score == 0.0
    assert "title filtered" in job.score_notes
    assert "filtered by title" in result.lower()


async def test_scan_registered_scanner_session_expired_adds_warning(tmp_db):
    init_db()
    from moonlighter.discovery.sources.base import ScannerSessionExpiredError

    result = await _run_scan([_raw(2)], linkedin_exc=ScannerSessionExpiredError("session expired"))
    assert "⚠️  _FakeBrowser: session expired" in result


async def test_scan_registered_scanner_generic_error_is_swallowed(tmp_db):
    init_db()
    result = await _run_scan([_raw(3)], linkedin_exc=RuntimeError("boom"))
    # a generic scanner error doesn't become a warning nor block the HTTP results
    assert "_FakeBrowser" not in result
    assert Job.get(Job.url == "https://x.com/scan/3").status == "new"


async def test_scan_unexpected_eval_error_stops_conservatively(tmp_db):
    init_db()
    result = await _run_scan(
        [_raw(4)], eval_mock=AsyncMock(side_effect=ValueError("unexpected error"))
    )
    # a non-spend error is logged and propagated; the scan stops conservatively and
    # the ScanLog claim is released (no orphan) for a future retry.
    assert ScanLog.select().count() == 0
    assert "processed" in result or "No new jobs found" in result


async def test_scan_integrity_error_on_save_skips_silently(tmp_db):
    init_db()
    # Pre-creates a Job with the same URL (no entry in ScanLog) → the claim succeeds,
    # evaluates, but Job.create collides → IntegrityError → job is skipped (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/5", status="new")
    result = await _run_scan([_raw(5)])
    assert "processed" in result or "No new jobs found" in result


async def test_scan_title_filtered_integrity_error_skips_silently(tmp_db):
    init_db()
    # Title in the blocklist + pre-existing Job (no ScanLog) → the filter branch
    # tenta Job.create archived, colide → IntegrityError → pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/6", status="new")
    result = await _run_scan([_raw(6, title="Staff Accountant")])
    assert "processed" in result or "No new jobs found" in result


# ── concurrency with semaphore ───────────────────────────────────────────────


class _Tracker:
    """Caller that tracks the peak of concurrent LLM calls."""

    def __init__(self) -> None:
        self.current = 0
        self.peak = 0

    async def __call__(self, prompt: str, model: str, cache_prefix: str | None = None) -> str:
        self.current += 1
        self.peak = max(self.peak, self.current)
        await asyncio.sleep(0.01)
        self.current -= 1
        return '{"score": 8.0, "score_notes": "ok", "caveats": []}'


async def test_scan_concurrency_is_capped(tmp_db):
    init_db()
    caller = _Tracker()
    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 2,
        "scan_batch_size": 1,
        "title_blocklist": [],
    }
    jobs = [_raw(i) for i in range(6)]
    saved, spend_hit = await scan_service._evaluate_and_store(jobs, config, {}, caller)
    assert len(saved) == 6
    assert spend_hit is False
    assert caller.peak == 2


async def test_scan_stops_before_llm_after_spend_limit(tmp_db):
    init_db()
    calls = {"n": 0}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        raise RuntimeError("spend limit reached")

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 1,
        "scan_batch_size": 1,
        "title_blocklist": [],
    }
    jobs = [_raw(i) for i in range(5)]
    _saved, spend_hit = await scan_service._evaluate_and_store(jobs, config, {}, caller)
    assert spend_hit is True
    # concurrency=1: the 1st call detects the spend-limit and sets stop; the rest see
    # stop=True right after the semaphore and don't even call the LLM.
    assert calls["n"] == 1
    assert ScanLog.select().count() == 0  # all claims released


async def test_scan_chunk_skips_already_claimed_job(tmp_db):
    init_db()
    # Pre-inserts a claim for the URL → _claim returns False → job skipped without calling the LLM.
    ScanLog.create(job_url="https://x.com/scan/99", source="greenhouse")

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise AssertionError("LLM must not be called for an already-claimed job")

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 5,
        "scan_batch_size": 5,
        "title_blocklist": [],
    }
    saved, spend_hit = await scan_service._evaluate_and_store([_raw(99)], config, {}, caller)
    assert saved == []
    assert spend_hit is False
    assert ScanLog.select().count() == 1  # only the pre-existing claim


async def test_scan_batches_jobs_into_one_call(tmp_db):
    init_db()
    calls = {"n": 0}

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        calls["n"] += 1
        return (
            "["
            + ", ".join('{"score": 8.0, "score_notes": "ok", "caveats": []}' for _ in range(4))
            + "]"
        )

    config = {
        "score_threshold": 6.5,
        "eval_model": "m",
        "scan_concurrency": 5,
        "scan_batch_size": 4,
        "title_blocklist": [],
    }
    jobs = [_raw(i) for i in range(4)]
    saved, spend_hit = await scan_service._evaluate_and_store(jobs, config, {}, caller)
    assert len(saved) == 4
    assert spend_hit is False
    assert calls["n"] == 1  # 4 jobs, 1 batch, 1 call


# ── archive_stale_jobs ──────────────────────────────────────────────────────

from moonlighter.discovery.archive import ArchiveStaleJobsError, archive_stale_jobs  # noqa: E402
from moonlighter.discovery.staleness import StalenessResult  # noqa: E402


def _stale_job(tmp_db, **kwargs):
    defaults = {
        "source": "greenhouse",
        "company": "acme",
        "title": "Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "status": "new",
    }
    defaults.update(kwargs)
    return Job.create(**defaults)


async def test_archive_stale_jobs_raises_when_job_id_and_company_both_given(tmp_db):
    init_db()
    with pytest.raises(ArchiveStaleJobsError):
        await archive_stale_jobs(1, "acme", CONFIG)


async def test_archive_stale_jobs_no_eligible_jobs_returns_empty(tmp_db):
    init_db()
    result = await archive_stale_jobs(None, None, CONFIG)
    assert result.archived == []
    assert result.failed_companies == []


async def test_archive_stale_jobs_marks_stale_job_closed(tmp_db, monkeypatch):
    init_db()
    job = _stale_job(tmp_db)

    async def fake_find(jobs_by_company, scanners, config):
        return StalenessResult(stale=[job], failed_companies=[])

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    result = await archive_stale_jobs(None, None, CONFIG)

    saved = Job.get_by_id(job.id)
    assert saved.status == "closed"
    assert saved.closed_at is not None
    assert result.archived == [
        {"company": "acme", "title": "Engineer", "url": "https://boards.greenhouse.io/acme/jobs/1"}
    ]


async def test_archive_stale_jobs_reports_failed_companies(tmp_db, monkeypatch):
    init_db()
    _stale_job(tmp_db)

    async def fake_find(jobs_by_company, scanners, config):
        return StalenessResult(stale=[], failed_companies=["acme"])

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    result = await archive_stale_jobs(None, None, CONFIG)

    assert result.archived == []
    assert result.failed_companies == ["acme"]
    # job untouched
    job = Job.select().where(Job.company == "acme").get()
    assert job.status == "new"
    assert job.closed_at is None


async def test_archive_stale_jobs_filters_by_job_id(tmp_db, monkeypatch):
    init_db()
    target = _stale_job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/1")
    other = _stale_job(tmp_db, url="https://boards.greenhouse.io/acme/jobs/2")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(target.id, None, CONFIG)

    jobs_checked = seen_groups[0][("greenhouse", "acme")]
    assert [j.id for j in jobs_checked] == [target.id]
    assert other.id not in [j.id for j in jobs_checked]


async def test_archive_stale_jobs_filters_by_company_case_insensitive(tmp_db, monkeypatch):
    init_db()
    acme_job = _stale_job(tmp_db, company="acme", url="https://x.com/1")
    _stale_job(tmp_db, company="beta", url="https://x.com/2")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(None, "ACME", CONFIG)

    jobs_checked = seen_groups[0][("greenhouse", "acme")]
    assert [j.id for j in jobs_checked] == [acme_job.id]


async def test_archive_stale_jobs_excludes_resolved_statuses(tmp_db, monkeypatch):
    init_db()
    _stale_job(tmp_db, status="applied", url="https://x.com/1")
    _stale_job(tmp_db, status="closed", url="https://x.com/2")
    _stale_job(tmp_db, status="archived", url="https://x.com/3")

    seen_groups = []

    async def fake_find(jobs_by_company, scanners, config):
        seen_groups.append(jobs_by_company)
        return StalenessResult()

    monkeypatch.setattr("moonlighter.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(None, None, CONFIG)

    assert seen_groups[0] == {}


# ── _format_archive_result ──────────────────────────────────────────────────


def test_format_archive_result_empty():
    from moonlighter.discovery.archive import ArchiveResult, _format_archive_result

    assert _format_archive_result(ArchiveResult()) == "No closed jobs found."


def test_format_archive_result_archived_only():
    from moonlighter.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}]
    )
    formatted = _format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "acme / Engineer — https://x.com/1" in formatted


def test_format_archive_result_failed_only():
    from moonlighter.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(failed_companies=["acme"])
    formatted = _format_archive_result(result)
    assert "No closed jobs found." in formatted
    assert "Could not check: acme" in formatted


def test_format_archive_result_archived_and_failed():
    from moonlighter.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        failed_companies=["beta"],
    )
    formatted = _format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "Could not check: beta" in formatted


# ── Gupy dispatch (portal-wide keyword feed, LinkedIn-model, config-gated) ──


async def _collect(config):
    """Runs _collect_raw_jobs with no HTTP-registry scanners and no LinkedIn jobs,
    isolating the Gupy dispatch branch."""
    with (
        patch("moonlighter.discovery.service.build_http_scanners", return_value={}),
        patch("moonlighter.discovery.service.discover_entry_points", return_value=[]),
    ):
        return await scan_service._collect_raw_jobs("engineer", config, {})


async def test_collect_raw_jobs_skips_gupy_by_default():
    with patch("moonlighter.discovery.sources.http.GupyScanner") as MockGupy:
        MockGupy.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    MockGupy.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_gupy_when_config_enabled():
    gupy_job = RawJob(
        source="gupy", company="acme", title="Eng", url="https://acme.gupy.io/1", description="d"
    )
    with patch("moonlighter.discovery.sources.http.GupyScanner") as MockGupy:
        MockGupy.return_value.scan = AsyncMock(return_value=[gupy_job])
        raw_jobs, _ = await _collect({"scan_gupy": True})
    MockGupy.return_value.scan.assert_awaited_once_with(keywords="engineer")
    assert raw_jobs == [gupy_job]


async def test_collect_raw_jobs_skips_remoteok_by_default():
    with patch("moonlighter.discovery.sources.http.RemoteOKScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    MockScanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_remoteok_when_config_enabled():
    job = RawJob(source="remoteok", company="Acme", title="Eng", url="https://remoteok.com/1")
    with patch("moonlighter.discovery.sources.http.RemoteOKScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_remoteok": True})
    MockScanner.return_value.scan.assert_awaited_once_with()
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_remotive_by_default():
    with patch("moonlighter.discovery.sources.http.RemotiveScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    MockScanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_remotive_when_config_enabled():
    job = RawJob(source="remotive", company="Acme", title="Eng", url="https://remotive.com/1")
    with patch("moonlighter.discovery.sources.http.RemotiveScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_remotive": True})
    MockScanner.return_value.scan.assert_awaited_once_with()
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_wwr_by_default():
    with patch("moonlighter.discovery.sources.http.WeWorkRemotelyScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    MockScanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_wwr_when_config_enabled():
    job = RawJob(
        source="weworkremotely", company="Acme", title="Eng", url="https://weworkremotely.com/1"
    )
    with patch("moonlighter.discovery.sources.http.WeWorkRemotelyScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_wwr": True})
    MockScanner.return_value.scan.assert_awaited_once_with()
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_hn_whoishiring_by_default():
    with patch("moonlighter.discovery.sources.http.HNWhoIsHiringScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    MockScanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_hn_whoishiring_when_config_enabled():
    job = RawJob(
        source="hn_whoishiring",
        company="Acme",
        title="Eng",
        url="https://news.ycombinator.com/item?id=1",
    )
    with patch("moonlighter.discovery.sources.http.HNWhoIsHiringScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_hn_whoishiring": True})
    MockScanner.return_value.scan.assert_awaited_once_with()
    assert raw_jobs == [job]
