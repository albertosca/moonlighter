"""Testes de unidade do apply_service: detect_applier (loop real, sem mock),
archive_screenshots (early-return e exceção engolida) e os branches de
apply_jobs/confirm_apply que o caminho feliz do test_mcp_server não toca.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from gauntler.application import service as apply_service
from gauntler.application.answers.cv import CVNotFoundError
from gauntler.application.appliers.base import ApplicationDraft
from gauntler.application.appliers.greenhouse import GreenhouseApplier
from gauntler.application.service import _anomaly_reasons, _render_draft
from gauntler.core.db import Application, Job, init_db

CONFIG = {"screenshots_dir": "/tmp/gauntler-test-shots", "llm_model": "x", "email": {}}
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
    with patch("gauntler.application.service.shutil.move", side_effect=OSError("disk")):
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
        patch("gauntler.application.service.browser") as mock_browser,
        patch(
            "gauntler.application.service.generate_answers",
            new=AsyncMock(return_value=draft),
        ),
        patch("gauntler.application.service.detect_applier") as mock_detect,
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


# ── _anomaly_reasons: pure exfiltration-smell scan ──────────────────────────


def test_anomaly_flags_url_email_phone():
    assert _anomaly_reasons("see https://evil.test/x", [])
    assert _anomaly_reasons("mail me at a@b.com", [])
    assert _anomaly_reasons("call +55 81 99999-8888", [])


def test_anomaly_clean_answer_not_flagged():
    assert _anomaly_reasons("I admire the engineering culture here.", []) == []


def test_anomaly_flags_disproportionately_long():
    others = ["short one", "short two", "short three"]
    long = "x " * 200
    assert any("long" in r.lower() for r in _anomaly_reasons(long, others))


def test_anomaly_not_flagged_when_length_proportionate_to_peers():
    # >= 3 peers (so the median IS computed), but the answer is not disproportionately
    # long relative to them — covers the inner condition's false branch.
    others = ["a normal answer", "another normal one", "yet another normal answer"]
    assert _anomaly_reasons("a similarly sized normal answer", others) == []


def test_anomaly_length_needs_at_least_three_others():
    # Too few peers to compute a meaningful median → no length flag.
    assert all("long" not in r.lower() for r in _anomaly_reasons("x " * 200, ["short"]))


def test_anomaly_email_scan_is_linear_on_hostile_long_input():
    # A long non-matching run (no '@') must not trigger quadratic backtracking in the
    # email regex — the answer being scanned is attacker-shapeable LLM output. With the
    # unbounded pattern this call took seconds and grew super-linearly; the bounded
    # pattern resolves it in well under the timeout. We assert on behavior (not flagged
    # as an email, no crash) — completing at all is the regression guard.
    hostile = "a" * 100_000
    reasons = _anomaly_reasons(hostile, [])
    assert "contains an email address" not in reasons


def test_render_draft_highlights_anomalous_llm_answer_not_prepopulated_phone(tmp_db):
    init_db()
    draft = ApplicationDraft(
        job_id=1,
        answers={"Phone": "+55 81 99999-8888", "Why us?": "reach me at leak@evil.test"},
        form_fields=["Phone", "Why us?"],
        pre_populated_fields=frozenset({"Phone"}),
    )
    out = _render_draft(1, _job(), draft)
    # The LLM free-text answer with an email is flagged...
    assert "Why us?" in out and "⚠️" in out
    # ...but the statically-filled phone field is not the thing being flagged.
    assert out.index("⚠️") < out.index("**Why us?**")  # highlight is above the answers


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
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
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
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
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
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
    ):
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service._fill_open_page(
            page, job, {"Name": "Alberto"}, "/tmp/cv.pdf", cfg, PROFILE
        )
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
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=None)),
    ):
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service._fill_open_page(
            _page(job.url), job, {}, "/tmp/cv.pdf", cfg, PROFILE
        )
    assert result is None


# ── fill_application: branches ──────────────────────────────────────────────


async def test_fill_application_fills_stops_persists(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/fill")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    page = _page(job.url)
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "PREENCHIDA" in result
    assert "submit_application" in result
    assert str(tmp_path) in result  # path do screenshot deriva de screenshots_dir, não hardcode
    applier.submit.assert_not_called()  # NÃO submete
    saved = Application.get(Application.job == job)
    assert saved.status == "filled"
    assert saved.email_ref is not None  # ref persistido
    page.close.assert_awaited_once()  # sem falha => fecha normal


async def test_fill_application_blocks_on_needs_review(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nr2")
    Application.create(job=job, status="draft", form_data='{"Work auth?": "__NEEDS_REVIEW__"}')
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "NÃO submetida" in result or "aguardando sua decisão" in result
    assert Application.get(Application.job == job).status == "draft"  # não virou filled


async def test_fill_application_aborts_on_missing_cv(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nocv")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with patch(
        "gauntler.application.service.resolve_cv_path",
        side_effect=CVNotFoundError("cv.pdf não existe"),
    ):
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "Não preenchi" in result


async def test_fill_application_reports_failed_fields(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/fillfail")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto", "X": "y"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled", "X": "failed:not_found"})
    page = _page(job.url)
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "falha" in result.lower() and "X" in result
    mock_browser.hide_window.assert_awaited_once()
    mock_browser.show_window.assert_awaited_once()
    page.close.assert_not_awaited()  # aba fica aberta pro humano mexer


async def test_fill_application_no_draft(tmp_db, tmp_path):
    init_db()
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.fill_application(99999, None, cfg, PROFILE)
    assert "não encontrada" in result


async def test_fill_application_unknown_ats(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://unknown/jobs/2")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=None)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "ATS não reconhecido" in result
    page.close.assert_awaited_once()  # ATS desconhecido não precisa de ajuda humana


async def test_fill_application_handles_exception(tmp_db, tmp_path):
    """Erro inesperado em _fill_open_page é capturado e devolvido como mensagem de aviso."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/exc")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch(
            "gauntler.application.service._fill_open_page",
            new=AsyncMock(side_effect=RuntimeError("falha inesperada")),
        ),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "Erro ao preencher" in result
    assert "falha inesperada" in result
    page.close.assert_not_awaited()  # aba fica aberta pro humano mexer
    mock_browser.show_window.assert_awaited_once()


async def test_confirm_apply_survives_hide_window_failure(tmp_db, tmp_path):
    """hide_window (best-effort) lançando antes do try não deve derrubar o fluxo nem
    impedir o submit — a page continua sendo usada e fechada normalmente."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/hidefail")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        page = _page(job.url)
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock(side_effect=RuntimeError("cdp down"))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submetida e confirmada" in result
    page.close.assert_awaited_once()


async def test_confirm_apply_survives_show_window_failure_on_exception(tmp_db, tmp_path):
    """Se show_window (best-effort) lançar dentro do handler de exceção genérica de
    _submit_on_page, o erro do CDP não deve mascarar o erro original nem pular o
    revert de estado — confirm_apply continua devolvendo a mensagem amigável e
    revertendo app/job."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/cdpdown")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch(
            "gauntler.application.service._fill_open_page",
            new=AsyncMock(side_effect=RuntimeError("falha inesperada")),
        ),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock(side_effect=RuntimeError("cdp down"))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "Erro ao submeter" in result
    assert "falha inesperada" in result
    saved = Application.get(Application.job == job)
    assert saved.status == "draft"
    assert Job.get_by_id(job.id).status == "reviewed"
    mock_browser.show_window.assert_awaited_once()


# ── submit_application: branches ────────────────────────────────────────────


async def test_submit_application_requires_filled(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/notfilled")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.submit_application(job.id, cfg, PROFILE)
    assert "fill_application" in result
    assert Application.get(Application.job == job).status == "draft"  # não submeteu


async def test_submit_application_refills_and_submits(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/sub")
    Application.create(
        job=job, status="filled", form_data='{"Name": "Alberto"}', email_ref="abc123"
    )
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"}, submit="submitted")
    with (
        patch("gauntler.application.service.browser") as mock_browser,
        patch("gauntler.application.service.detect_applier", new=AsyncMock(return_value=applier)),
        patch("gauntler.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.submit_application(job.id, cfg, PROFILE)
    assert "submetida e confirmada" in result
    applier.submit.assert_awaited()
    assert Application.get(Application.job == job).status == "submitted"


async def test_submit_application_no_draft(tmp_db, tmp_path):
    init_db()
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.submit_application(99999, cfg, PROFILE)
    assert "não encontrada" in result


async def test_submit_application_missing_cv(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/subnocv")
    Application.create(job=job, status="filled", form_data='{"Name": "Alberto"}', email_ref="r")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with patch(
        "gauntler.application.service.resolve_cv_path",
        side_effect=CVNotFoundError("cv.pdf não existe"),
    ):
        result = await apply_service.submit_application(job.id, cfg, PROFILE)
    assert "Não submeti" in result
