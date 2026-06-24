"""Testes do scan_service focados em add_job (vaga manual) e nos branches de
borda do scan_and_evaluate que não passam pelo caminho feliz do test_mcp_server.

add_job é chamado direto no service (não pela tool MCP) para isolar a lógica de
config/profile/caller, sem depender da config global carregada no import.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from candidatador.core.db import Job, ScanLog, init_db
from candidatador.discovery import service as scan_service
from candidatador.discovery.evaluator import EvaluationResult

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
        patch("candidatador.discovery.service.httpx.AsyncClient", return_value=acm),
        patch(
            "candidatador.discovery.service.evaluate_job",
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
    with patch("candidatador.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/3", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "404" in result


async def test_add_job_http_exception_returns_error(tmp_db):
    init_db()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    acm.__aexit__ = AsyncMock(return_value=False)
    with patch("candidatador.discovery.service.httpx.AsyncClient", return_value=acm):
        result = await scan_service.add_job(
            "https://x.com/4", "Stripe", "Engineer", "", CONFIG, PROFILE, MagicMock()
        )
    assert "Erro ao buscar URL" in result


# ── deduplicação ────────────────────────────────────────────────────────────


async def test_add_job_dedup_existing_job(tmp_db):
    init_db()
    Job.create(
        source="manual", company="Stripe", title="Eng", url="https://x.com/5",
        score=8.0, status="new",
    )
    ScanLog.create(job_url="https://x.com/5", source="manual")
    result = await scan_service.add_job(
        "https://x.com/5", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "já existe" in result


async def test_add_job_scanlog_without_job_proceeds_to_eval(tmp_db):
    init_db()
    # ScanLog tem a URL mas não há Job (estado inconsistente raro) → o dedup deixa
    # passar (Job.get levanta DoesNotExist), avalia, mas o ScanLog.create final
    # colide com o registro existente → IntegrityError → mensagem de conflito.
    ScanLog.create(job_url="https://x.com/6", source="manual")
    with patch(
        "candidatador.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/6", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "conflito de URL" in result


# ── filtro de título ────────────────────────────────────────────────────────


async def test_add_job_title_blocklist_archives(tmp_db):
    init_db()
    result = await scan_service.add_job(
        "https://x.com/7", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "descartada pelo filtro" in result
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
    assert "descartada pelo filtro" in result


# ── avaliação e persistência ────────────────────────────────────────────────


async def test_add_job_new_above_threshold_with_caveats(tmp_db):
    init_db()
    with patch(
        "candidatador.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(9.0, caveats=["visa", "relocation"])),
    ):
        result = await scan_service.add_job(
            "https://x.com/9", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "NEW" in result
    assert "visa" in result and "relocation" in result
    assert Job.get(Job.url == "https://x.com/9").status == "new"


async def test_add_job_below_threshold_archived(tmp_db):
    init_db()
    with patch(
        "candidatador.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(3.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/10", "Acme", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "arquivada" in result
    assert "nenhum" in result  # sem caveats
    assert Job.get(Job.url == "https://x.com/10").status == "archived"


async def test_add_job_integrity_conflict_on_create(tmp_db):
    init_db()
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/11", status="new")
    with patch(
        "candidatador.discovery.service.evaluate_job",
        new=AsyncMock(return_value=_eval(8.0)),
    ):
        result = await scan_service.add_job(
            "https://x.com/11", "Stripe", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert "conflito de URL" in result


# ── branches de borda do scan_and_evaluate ──────────────────────────────────

from candidatador.discovery.sources.base import RawJob  # noqa: E402


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
    """
    cfg = config or {**CONFIG, "title_blocklist": ["staff accountant"]}
    eval_mock = eval_mock or AsyncMock(return_value=_eval(8.0))
    with (
        patch("candidatador.discovery.service.GreenhouseScanner") as MockGH,
        patch("candidatador.discovery.service.LeverScanner") as MockLV,
        patch("candidatador.discovery.service.AshbyScanner") as MockAB,
        patch("candidatador.discovery.service.browser") as mock_browser,
        patch("candidatador.discovery.service.evaluate_job", new=eval_mock),
        patch("candidatador.discovery.sources.playwright.LinkedInScanner") as MockLI,
        patch("candidatador.discovery.service.load_company_list", return_value={"greenhouse": ["co"]}),
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
    assert "descartada" in result.lower() or "descartadas" in result.lower()


async def test_scan_linkedin_session_expired_adds_warning(tmp_db):
    init_db()
    from candidatador.discovery.sources.playwright import LinkedInSessionExpiredError

    result = await _run_scan(
        [_raw(2)], linkedin_exc=LinkedInSessionExpiredError("sessão expirada")
    )
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
    assert "processadas" in result or "Nenhuma" in result


async def test_scan_integrity_error_on_save_skips_silently(tmp_db):
    init_db()
    # Pré-cria um Job com a mesma URL (sem entrada no ScanLog) → o claim sucede,
    # avalia, mas Job.create colide → IntegrityError → vaga é pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/5", status="new")
    result = await _run_scan([_raw(5)])
    assert "processadas" in result or "Nenhuma" in result


async def test_scan_title_filtered_integrity_error_skips_silently(tmp_db):
    init_db()
    # Título na blocklist + Job pré-existente (sem ScanLog) → o branch de filtro
    # tenta Job.create archived, colide → IntegrityError → pulada (return None).
    Job.create(source="x", company="x", title="x", url="https://x.com/scan/6", status="new")
    result = await _run_scan([_raw(6, title="Staff Accountant")])
    assert "processadas" in result or "Nenhuma" in result
