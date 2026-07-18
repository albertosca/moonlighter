"""Testes do scan_service focados em add_job (vaga manual) e nos branches de
borda do scan_and_evaluate que não passam pelo caminho feliz do test_mcp_server.

add_job é chamado direto no service (não pela tool MCP) para isolar a lógica de
config/profile/caller, sem depender da config global carregada no import.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gauntler.core.db import Job, ScanLog, init_db
from gauntler.discovery import service as scan_service
from gauntler.discovery.evaluator import EvaluationResult

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
    """Monta um AsyncClient mockado que serve como context manager assíncrono."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=status_code, text=text))
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=client)
    acm.__aexit__ = AsyncMock(return_value=False)
    return acm, client


# ── validação de entrada ────────────────────────────────────────────────────


async def test_add_job_missing_company_title(tmp_db):
    init_db()
    result = await scan_service.add_job(
        "https://x.com/1", "", "", "desc fornecida", CONFIG, PROFILE, MagicMock()
    )
    assert "company" in result and "title" in result


# ── busca automática de descrição via HTTP ──────────────────────────────────


async def test_add_job_fetches_description_when_empty(tmp_db):
    init_db()
    acm, _ = _http_client(text="<html><body>Real desc</body></html>")
    with (
        patch("gauntler.discovery.service.httpx.AsyncClient", return_value=acm),
        patch(
            "gauntler.discovery.service.evaluate_job",
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
    with patch("gauntler.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/3", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "404" in result


async def test_add_job_http_exception_returns_error(tmp_db):
    init_db()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    acm.__aexit__ = AsyncMock(return_value=False)
    with patch("gauntler.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/4", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "Error fetching URL" in result


# ── deduplicação ────────────────────────────────────────────────────────────


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
    # ScanLog tem a URL mas não há Job (estado inconsistente raro) → o dedup deixa
    # passar (Job.get levanta DoesNotExist), avalia, mas o ScanLog.create final
    # colide com o registro existente → IntegrityError → mensagem de conflito.
    ScanLog.create(job_url="https://x.com/6", source="manual")
    with patch(
        "gauntler.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/6", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


# ── filtro de título ────────────────────────────────────────────────────────


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
    # Pré-cria a URL para forçar IntegrityError no Job.create do branch de blocklist.
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/8", status="new")
    result = await scan_service.add_job(
        "https://x.com/8", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "discarded by the title filter" in result


# ── avaliação e persistência ────────────────────────────────────────────────


async def test_add_job_new_above_threshold_with_caveats(tmp_db):
    init_db()
    with patch(
        "gauntler.discovery.service.evaluate_job",
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
        "gauntler.discovery.service.evaluate_job",
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
        "gauntler.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/11", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "URL conflict" in result


# ── branches de borda do scan_and_evaluate ──────────────────────────────────

from gauntler.discovery.sources.base import RawJob  # noqa: E402


def _raw(i, title="Engineer", source="greenhouse"):
    return RawJob(
        source=source,
        company=f"Co{i}",
        title=title,
        url=f"https://x.com/scan/{i}",
        description="desc",
    )


async def _run_scan(raws, *, eval_mock=None, linkedin_exc=None, linkedin_jobs=None, config=None):
    """Roda scan_and_evaluate com scanners HTTP mockados servindo `raws`.

    linkedin_exc: exceção que o LinkedInScanner.scan deve levantar.
    linkedin_jobs: lista de RawJob que o LinkedInScanner.scan deve retornar.
    Se ambos forem None, simula ausência de browser (new_page falha).

    eval_mock: AsyncMock aplicado por vaga dentro do lote. Pode ser
    AsyncMock(return_value=EvaluationResult) ou AsyncMock(side_effect=exc).
    """
    cfg = config or {**CONFIG, "title_blocklist": ["staff accountant"]}
    _eval_per_job = eval_mock or AsyncMock(return_value=_eval(8.0))

    async def _batch(jobs, profile, model, caller):
        # Aplica eval_mock a cada vaga do lote; erros propagam para evaluate_chunk.
        return [await _eval_per_job(j.company, model) for j in jobs]

    with (
        patch("gauntler.discovery.sources.http.GreenhouseScanner") as MockGH,
        patch("gauntler.discovery.sources.http.LeverScanner") as MockLV,
        patch("gauntler.discovery.sources.http.AshbyScanner") as MockAB,
        patch("gauntler.discovery.service.browser") as mock_browser,
        patch("gauntler.discovery.service.evaluate_jobs_batch", new=_batch),
        patch("gauntler.discovery.sources.playwright.LinkedInScanner") as MockLI,
        patch("gauntler.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}),
    ):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        if linkedin_exc is None and linkedin_jobs is None:
            mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        else:
            mock_browser.new_page = AsyncMock(return_value=AsyncMock())
            if linkedin_exc is not None:
                MockLI.return_value.scan = AsyncMock(side_effect=linkedin_exc)
            else:
                MockLI.return_value.scan = AsyncMock(return_value=linkedin_jobs)
        return await scan_service.scan_and_evaluate("", "all", cfg, PROFILE, MagicMock())


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


async def test_scan_linkedin_session_expired_adds_warning(tmp_db):
    init_db()
    from gauntler.discovery.sources.playwright import LinkedInSessionExpiredError

    result = await _run_scan([_raw(2)], linkedin_exc=LinkedInSessionExpiredError("sessão expirada"))
    assert "LinkedIn" in result


async def test_scan_linkedin_generic_error_is_swallowed(tmp_db):
    init_db()
    result = await _run_scan([_raw(3)], linkedin_exc=RuntimeError("boom"))
    # erro genérico do LinkedIn não vira warning nem bloqueia os resultados HTTP
    assert "LinkedIn" not in result
    assert Job.get(Job.url == "https://x.com/scan/3").status == "new"


async def test_scan_unexpected_eval_error_stops_conservatively(tmp_db):
    init_db()
    result = await _run_scan(
        [_raw(4)], eval_mock=AsyncMock(side_effect=ValueError("erro inesperado"))
    )
    # erro não-spend é logado e propagado; o scan para conservadoramente e o
    # claim do ScanLog é liberado (sem órfão) p/ retry futuro.
    assert ScanLog.select().count() == 0
    assert "processed" in result or "No new jobs found" in result


async def test_scan_integrity_error_on_save_skips_silently(tmp_db):
    init_db()
    # Pré-cria um Job com a mesma URL (sem entrada no ScanLog) → o claim sucede,
    # avalia, mas Job.create colide → IntegrityError → vaga é pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/5", status="new")
    result = await _run_scan([_raw(5)])
    assert "processed" in result or "No new jobs found" in result


async def test_scan_title_filtered_integrity_error_skips_silently(tmp_db):
    init_db()
    # Título na blocklist + Job pré-existente (sem ScanLog) → o branch de filtro
    # tenta Job.create archived, colide → IntegrityError → pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/6", status="new")
    result = await _run_scan([_raw(6, title="Staff Accountant")])
    assert "processed" in result or "No new jobs found" in result


# ── concorrência com semaphore ───────────────────────────────────────────────


class _Tracker:
    """Caller que rastreia pico de chamadas LLM simultâneas."""

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
    # concurrency=1: a 1ª call detecta o spend-limit e seta stop; as demais veem
    # stop=True logo após o semaphore e nem chamam o LLM.
    assert calls["n"] == 1
    assert ScanLog.select().count() == 0  # todos os claims liberados


async def test_scan_chunk_skips_already_claimed_job(tmp_db):
    init_db()
    # Pré-insere claim para a URL → _claim retorna False → vaga pulada sem chamar o LLM.
    ScanLog.create(job_url="https://x.com/scan/99", source="greenhouse")

    async def caller(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise AssertionError("LLM não deve ser chamado para vaga já reservada")

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
    assert ScanLog.select().count() == 1  # apenas o claim pré-existente


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
    assert calls["n"] == 1  # 4 vagas, 1 lote, 1 chamada


# ── archive_stale_jobs ──────────────────────────────────────────────────────

from gauntler.discovery.archive import ArchiveStaleJobsError, archive_stale_jobs  # noqa: E402
from gauntler.discovery.staleness import StalenessResult  # noqa: E402


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

    monkeypatch.setattr("gauntler.discovery.archive.find_stale_jobs", fake_find)
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

    monkeypatch.setattr("gauntler.discovery.archive.find_stale_jobs", fake_find)
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

    monkeypatch.setattr("gauntler.discovery.archive.find_stale_jobs", fake_find)
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

    monkeypatch.setattr("gauntler.discovery.archive.find_stale_jobs", fake_find)
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

    monkeypatch.setattr("gauntler.discovery.archive.find_stale_jobs", fake_find)
    await archive_stale_jobs(None, None, CONFIG)

    assert seen_groups[0] == {}


# ── _format_archive_result ──────────────────────────────────────────────────


def test_format_archive_result_empty():
    from gauntler.discovery.archive import ArchiveResult, _format_archive_result

    assert _format_archive_result(ArchiveResult()) == "No closed jobs found."


def test_format_archive_result_archived_only():
    from gauntler.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}]
    )
    formatted = _format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "acme / Engineer — https://x.com/1" in formatted


def test_format_archive_result_failed_only():
    from gauntler.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(failed_companies=["acme"])
    formatted = _format_archive_result(result)
    assert "No closed jobs found." in formatted
    assert "Could not check: acme" in formatted


def test_format_archive_result_archived_and_failed():
    from gauntler.discovery.archive import ArchiveResult, _format_archive_result

    result = ArchiveResult(
        archived=[{"company": "acme", "title": "Engineer", "url": "https://x.com/1"}],
        failed_companies=["beta"],
    )
    formatted = _format_archive_result(result)
    assert "1 job(s) archived" in formatted
    assert "Could not check: beta" in formatted
