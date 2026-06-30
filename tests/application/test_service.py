"""Testes de unidade do apply_service: detect_applier (loop real, sem mock),
archive_screenshots (early-return e exceção engolida) e os branches de
apply_jobs/confirm_apply que o caminho feliz do test_mcp_server não toca.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from candidatador.application import service as apply_service
from candidatador.application.appliers.base import ApplicationDraft
from candidatador.application.appliers.greenhouse import GreenhouseApplier
from candidatador.core.db import Application, Job, init_db

CONFIG = {"screenshots_dir": "/tmp/candidatador-test-shots", "llm_model": "x", "email": {}}
PROFILE: dict = {}


def _page(url):
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    return page


def _job(**kw):
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Eng",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "score": 8.0,
        "status": "new",
    }
    defaults.update(kw)
    return Job.create(**defaults)


# ── detect_applier (loop real) ──────────────────────────────────────────────


async def test_detect_applier_matches_greenhouse(tmp_db):
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://boards.greenhouse.io/stripe/jobs/1"), CONFIG, PROFILE
    )
    assert isinstance(applier, GreenhouseApplier)


async def test_detect_applier_returns_none_for_unknown(tmp_db):
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://unknown-ats.example/jobs/1"), CONFIG, PROFILE
    )
    assert applier is None


# ── archive_screenshots ─────────────────────────────────────────────────────


def test_archive_screenshots_noop_when_missing(tmp_path):
    # src não existe → retorna sem erro
    apply_service.archive_screenshots(123, {"screenshots_dir": str(tmp_path)})


def test_archive_screenshots_swallows_exception(tmp_path):
    src = tmp_path / "456"
    src.mkdir()
    with patch("candidatador.application.service.shutil.move", side_effect=OSError("disk")):
        # exceção é logada como não-crítica, não propaga
        apply_service.archive_screenshots(456, {"screenshots_dir": str(tmp_path)})


# ── apply_jobs: bloco needs_review ──────────────────────────────────────────


async def test_apply_jobs_shows_needs_review_fields(tmp_db):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nr")
    draft = ApplicationDraft(
        job_id=job.id,
        answers={"Work auth?": "__NEEDS_REVIEW__", "Name": "Alberto"},
        form_fields=["Work auth?", "Name"],
    )
    with (
        patch("candidatador.application.service.browser") as mock_browser,
        patch(
            "candidatador.application.service.generate_answers",
            new=AsyncMock(return_value=draft),
        ),
        patch("candidatador.application.service.detect_applier") as mock_detect,
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.save_screenshot = AsyncMock()
        applier = AsyncMock()
        applier.extract_fields = AsyncMock(return_value=["Work auth?", "Name"])
        mock_detect.return_value = applier
        result = await apply_service.apply_jobs([job.id], CONFIG, PROFILE, MagicMock())
    assert "PRECISAM DA SUA DECISÃO" in result
    assert "Work auth?" in result
    # campo NEEDS_REVIEW não é renderizado como resposta normal, mas Name sim
    assert "Alberto" in result


# ── confirm_apply: branches ─────────────────────────────────────────────────


def _confirm_mocks(job, *, fill_status, submit="submitted"):
    applier = AsyncMock()
    applier.fill_form = AsyncMock(return_value=fill_status)
    applier.submit = AsyncMock(return_value=submit)
    return applier


async def test_confirm_apply_without_email_config_skips_alias(tmp_db, tmp_path):
    """config sem email.address → não injeta alias (branch falso de `if base_address`)."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/noemail")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x"}  # sem chave "email"
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    with (
        patch("candidatador.application.service.browser") as mock_browser,
        patch("candidatador.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("candidatador.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submetida e confirmada" in result


async def test_confirm_apply_logs_failed_fields_but_submits(tmp_db, tmp_path):
    """Campos com falha no preenchimento geram warning mas não impedem submit confirmado."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/partial")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto", "X": "y"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled", "X": "failed:not_found"})
    with (
        patch("candidatador.application.service.browser") as mock_browser,
        patch("candidatador.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("candidatador.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submetida e confirmada" in result
    assert Application.get(Application.job == job).status == "submitted"


# ── _fill_open_page ─────────────────────────────────────────────────────────


async def test_fill_open_page_fills_and_screenshots_without_submit(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/fop")
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("candidatador.application.service.browser") as mock_browser,
        patch("candidatador.application.service.detect_applier", new=AsyncMock(return_value=applier)),
    ):
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service._fill_open_page(page, job, {"Name": "Alberto"}, "/tmp/cv.pdf", cfg, PROFILE)
    assert result is not None
    returned_applier, fill_status = result
    assert returned_applier is applier
    assert fill_status == {"Name": "filled"}
    applier.submit.assert_not_called()
    page.close.assert_not_called()  # o helper NÃO fecha a página
    mock_browser.save_screenshot.assert_awaited()  # screenshot 03 tirado


async def test_fill_open_page_returns_none_for_unknown_ats(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://unknown/jobs/1")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with (
        patch("candidatador.application.service.browser") as mock_browser,
        patch("candidatador.application.service.detect_applier", new=AsyncMock(return_value=None)),
    ):
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service._fill_open_page(_page(job.url), job, {}, "/tmp/cv.pdf", cfg, PROFILE)
    assert result is None
