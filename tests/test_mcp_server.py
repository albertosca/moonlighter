import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from candidatador.db import init_db, Job, Application, ScanLog
from candidatador.evaluator import EvaluationResult
from candidatador.applicator.base import ApplicationDraft
from candidatador.applicator.linkedin import LinkedInApplier


# ── helpers ───────────────────────────────────────────────────────────────────

def make_eval_result(score=8.0):
    return EvaluationResult(
        score=score, score_notes="Good match.",
        caveats=[], salary_min=150000, salary_max=200000,
        salary_currency="USD", salary_source="llm_estimate",
    )


def create_job(tmp_db, **kwargs):
    """Helper: creates a job in the temp DB. Call init_db() first."""
    defaults = dict(
        source="greenhouse", company="Stripe", title="Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/1",
        score=8.0, status="new",
    )
    defaults.update(kwargs)
    return Job.create(**defaults)


def create_application(job, **kwargs):
    defaults = dict(status="draft", form_data='{"Q": "A"}')
    defaults.update(kwargs)
    return Application.create(job=job, **defaults)


# ── scan_and_evaluate ─────────────────────────────────────────────────────────

async def test_scan_no_new_jobs(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser:
        for M in (MockGH, MockLV, MockAB):
            instance = AsyncMock()
            instance.scan = AsyncMock(return_value=[])
            M.return_value = instance
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate()
    assert "Nenhuma vaga nova" in result


async def test_scan_all_below_threshold(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/1", description="desc")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=4.0))):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate()
    assert "threshold" in result.lower()
    # Job should be archived
    job = Job.get(Job.url == "https://x.com/1")
    assert job.status == "archived"


async def test_scan_above_threshold_shows_table(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="Stripe", title="Sr Eng", url="https://x.com/2", description="desc")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=8.0))):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate()
    assert "Stripe" in result
    assert "Sr Eng" in result


async def test_scan_dedup_against_scan_log(tmp_db):
    init_db()
    ScanLog.create(job_url="https://x.com/3", source="greenhouse")
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/3")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job") as mock_eval:
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        result = await scan_and_evaluate()
    mock_eval.assert_not_called()
    assert "Nenhuma vaga nova" in result


async def test_scan_linkedin_failure_doesnt_block(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/4", description="desc")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=8.0))):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("LinkedIn not available"))
        result = await scan_and_evaluate()
    # Should still return HTTP results
    assert "co" in result or "Eng" in result or "vagas" in result.lower()


async def test_scan_saves_salary_fields(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="Stripe", title="Eng", url="https://x.com/5", description="desc")
    eval_result = EvaluationResult(score=8.0, score_notes="ok", caveats=[], salary_min=180000, salary_max=220000, salary_currency="USD", salary_source="stated")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=eval_result)):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate()
    job = Job.get(Job.url == "https://x.com/5")
    assert job.salary_min == 180000
    assert job.salary_currency == "USD"
    assert job.salary_source == "stated"


async def test_scan_saves_caveats_as_json(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/6", description="desc")
    eval_result = EvaluationResult(score=7.0, score_notes="ok", caveats=["US only", "requires visa"])
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=eval_result)):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate()
    job = Job.get(Job.url == "https://x.com/6")
    caveats = json.loads(job.caveats)
    assert "US only" in caveats
    assert "requires visa" in caveats


async def test_scan_status_archived_if_below_threshold(tmp_db):
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    raw = RawJob(source="greenhouse", company="co", title="Eng", url="https://x.com/7", description="desc")
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=3.0))):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate()
    job = Job.get(Job.url == "https://x.com/7")
    assert job.status == "archived"


# ── list_jobs ─────────────────────────────────────────────────────────────────

async def test_list_jobs_default_new(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj1", status="new", score=8.0)
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="new")
    assert "Stripe" in result


async def test_list_jobs_filtered_by_status(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj2", status="reviewed", score=7.0, company="Linear")
    create_job(tmp_db, url="https://x.com/lj3", status="new", score=8.0, company="Vercel")
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="reviewed")
    assert "Linear" in result
    assert "Vercel" not in result


async def test_list_jobs_limit(tmp_db):
    init_db()
    for i in range(5):
        create_job(tmp_db, url=f"https://x.com/lj-limit-{i}", status="new", score=float(i), company=f"Co{i}")
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="new", limit=3)
    # Verify it returned without error
    assert result is not None
    assert len(result) > 0


async def test_list_jobs_empty(tmp_db):
    init_db()
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="offer")
    assert "Nenhuma vaga" in result


async def test_list_jobs_ordered_by_score_desc(tmp_db):
    init_db()
    create_job(tmp_db, url="https://x.com/lj-lo", status="new", score=6.0, company="LowScore")
    create_job(tmp_db, url="https://x.com/lj-hi", status="new", score=9.5, company="HighScore")
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="new")
    # HighScore should appear before LowScore in the output
    assert result.index("HighScore") < result.index("LowScore")


# ── get_job ───────────────────────────────────────────────────────────────────

async def test_get_job_existing(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj1")
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    assert "Stripe" in result
    assert "Engineer" in result
    assert str(job.id) in result or "8.0" in result


async def test_get_job_nonexistent(tmp_db):
    init_db()
    from candidatador.mcp_server import get_job
    result = await get_job(id=99999)
    assert "não encontrada" in result


async def test_get_job_with_caveats(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj2", caveats='["US only"]')
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    assert "US only" in result


async def test_get_job_with_salary(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj3", salary_min=150000, salary_max=200000, salary_currency="USD", salary_source="stated")
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    assert "150" in result or "200" in result


async def test_get_job_without_salary(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj4")
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    # Should not crash; salary line absent
    assert "não encontrada" not in result


async def test_get_job_without_posted_at(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj5", posted_at=None)
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    assert "n/d" in result


# ── apply_jobs ────────────────────────────────────────────────────────────────

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


async def test_apply_jobs_creates_draft(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/apply1")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/apply1")
    draft = ApplicationDraft(job_id=job.id, answers={"Q": "A"}, form_fields=["Q"])
    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.generate_answers", new=AsyncMock(return_value=draft)), \
         patch("candidatador.mcp_server._detect_applier") as mock_detect:
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.extract_fields = AsyncMock(return_value=["Q"])
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import apply_jobs
        result = await apply_jobs(ids=[job.id])
    app = Application.get(Application.job == job)
    assert app.status == "draft"
    assert "Q" in result or "Rascunho" in result


async def test_apply_jobs_job_not_found(tmp_db):
    init_db()
    from candidatador.mcp_server import apply_jobs
    result = await apply_jobs(ids=[99999])
    assert "não encontrada" in result


async def test_apply_jobs_unknown_ats(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://unknownats.com/jobs/1")
    page = make_mock_page(url="https://unknownats.com/jobs/1")
    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier", new=AsyncMock(return_value=None)):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        from candidatador.mcp_server import apply_jobs
        result = await apply_jobs(ids=[job.id])
    assert "ATS não reconhecido" in result


async def test_apply_jobs_updates_job_status(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/apply2")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/apply2")
    draft = ApplicationDraft(job_id=job.id, answers={"Q": "A"}, form_fields=["Q"])
    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.generate_answers", new=AsyncMock(return_value=draft)), \
         patch("candidatador.mcp_server._detect_applier") as mock_detect:
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.extract_fields = AsyncMock(return_value=["Q"])
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import apply_jobs
        await apply_jobs(ids=[job.id])
    job_fresh = Job.get_by_id(job.id)
    assert job_fresh.status == "applying"


# ── confirm_apply ─────────────────────────────────────────────────────────────

async def test_confirm_apply_success(tmp_db, tmp_path):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca1", status="applying")
    app = create_application(job)
    # Create a fake cv.pdf
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/ca1")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.fill_form = AsyncMock()
        mock_applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)

    app_fresh = Application.get_by_id(app.id)
    assert app_fresh.status == "submitted"
    job_fresh = Job.get_by_id(job.id)
    assert job_fresh.status == "applied"
    assert "✓" in result or "submetida" in result


async def test_confirm_apply_no_application(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca2")
    # No application created
    from candidatador.mcp_server import confirm_apply
    result = await confirm_apply(job_id=job.id)
    assert "sem rascunho" in result or "não encontrada" in result


async def test_confirm_apply_job_not_found(tmp_db):
    init_db()
    from candidatador.mcp_server import confirm_apply
    result = await confirm_apply(job_id=88888)
    assert "não encontrada" in result or "sem rascunho" in result


async def test_confirm_apply_cv_not_found(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca3", status="applying")
    app = create_application(job)
    with patch("candidatador.mcp_server.os.path.exists", return_value=False):
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)
    assert "CV não encontrado" in result


async def test_confirm_apply_merges_answer_overrides(tmp_db, tmp_path):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca4", status="applying")
    app = create_application(job, form_data='{"Q1": "original", "Q2": "original2"}')
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/ca4")

    fill_calls = []
    async def fake_fill(answers, cv):
        fill_calls.append(answers.copy())

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = MagicMock()
        mock_applier.fill_form = fake_fill
        mock_applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        await confirm_apply(job_id=job.id, answers={"Q1": "overridden"})

    assert fill_calls[0]["Q1"] == "overridden"
    assert fill_calls[0]["Q2"] == "original2"


async def test_confirm_apply_injects_email_alias(tmp_db, tmp_path):
    """BUG-01: confirm_apply deve injetar candidaturas+<ref>@... no campo de
    email do formulário, para que respostas da empresa caiam na conta monitorada e
    carreguem o ref de rastreamento."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/alias1", status="applying")
    app = create_application(job, form_data='{"Email": "pessoal@gmail.com", "Q1": "x"}')
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/alias1")

    fill_calls = []
    async def fake_fill(answers, cv):
        fill_calls.append(answers.copy())

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = MagicMock()
        mock_applier.fill_form = fake_fill
        mock_applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply, _build_email_alias, _config
        await confirm_apply(job_id=job.id)

    app_fresh = Application.get_by_id(app.id)
    assert app_fresh.email_ref  # ref foi gerado
    expected = _build_email_alias(_config["email"]["address"], app_fresh.email_ref)
    assert fill_calls[0]["Email"] == expected
    assert "+" in fill_calls[0]["Email"]


async def test_confirm_apply_exception_reverts_status(tmp_db, tmp_path):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca5", status="applying")
    app = create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/ca5")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = MagicMock()
        mock_applier.fill_form = AsyncMock(side_effect=Exception("browser crash"))
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)

    app_fresh = Application.get_by_id(app.id)
    assert app_fresh.status == "draft"
    job_fresh = Job.get_by_id(job.id)
    assert job_fresh.status == "reviewed"
    assert "Erro" in result or "⚠️" in result


# ── retry_apply ───────────────────────────────────────────────────────────────

async def test_retry_apply_no_draft(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ra1")
    from candidatador.mcp_server import retry_apply
    result = await retry_apply(job_id=job.id)
    assert "apply_jobs" in result or "primeiro" in result


async def test_retry_apply_calls_confirm_apply(tmp_db, tmp_path):
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ra2", status="applying")
    create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/ra2")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.fill_form = AsyncMock()
        mock_applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import retry_apply
        result = await retry_apply(job_id=job.id)
    assert "submetida" in result or "✓" in result


# ── get_pipeline ──────────────────────────────────────────────────────────────

async def test_get_pipeline_empty(tmp_db):
    init_db()
    from candidatador.mcp_server import get_pipeline
    result = await get_pipeline()
    assert "0" in result or "Total" in result


async def test_get_pipeline_groups_by_status(tmp_db):
    init_db()
    job1 = create_job(tmp_db, url="https://x.com/pl1", company="Stripe")
    job2 = create_job(tmp_db, url="https://x.com/pl2", company="Linear")
    create_application(job1, status="submitted")
    create_application(job2, status="interviews")
    from candidatador.mcp_server import get_pipeline
    result = await get_pipeline()
    assert "Submitted" in result or "submitted" in result.lower()
    assert "Interview" in result or "interview" in result.lower()


async def test_get_pipeline_shows_next_action(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl3")
    create_application(job, status="submitted", next_action="follow up em 2026-06-01")
    from candidatador.mcp_server import get_pipeline
    result = await get_pipeline()
    assert "follow up" in result


async def test_get_pipeline_skips_empty_statuses(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/pl4")
    create_application(job, status="submitted")
    from candidatador.mcp_server import get_pipeline
    result = await get_pipeline()
    # "Offer" section should not appear since no offer apps
    assert "## Offer" not in result


# ── update_status ─────────────────────────────────────────────────────────────

async def test_update_status_success(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us1")
    create_application(job)
    from candidatador.mcp_server import update_status
    result = await update_status(job_id=job.id, status="screening")
    app = Application.get(Application.job == job)
    assert app.status == "screening"
    assert "screening" in result


async def test_update_status_with_notes(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us2")
    create_application(job)
    from candidatador.mcp_server import update_status
    await update_status(job_id=job.id, status="interviews", notes="Scheduled for Monday")
    app = Application.get(Application.job == job)
    assert "Scheduled for Monday" in app.notes


async def test_update_status_with_next_action(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us3")
    create_application(job)
    from candidatador.mcp_server import update_status
    result = await update_status(job_id=job.id, status="screening", next_action="Call Friday")
    app = Application.get(Application.job == job)
    assert app.next_action == "Call Friday"
    assert "Call Friday" in result


async def test_update_status_invalid(tmp_db):
    init_db()
    from candidatador.mcp_server import update_status
    result = await update_status(job_id=1, status="banana")
    assert "inválido" in result or "Status" in result


async def test_update_status_job_not_found(tmp_db):
    init_db()
    from candidatador.mcp_server import update_status
    result = await update_status(job_id=77777, status="screening")
    assert "não encontrada" in result


async def test_update_status_no_application(tmp_db):
    init_db()
    job = create_job(tmp_db, url="https://x.com/us5")
    # No application
    from candidatador.mcp_server import update_status
    result = await update_status(job_id=job.id, status="screening")
    assert "candidatura" in result or "não encontrada" in result


# ── scan_and_evaluate: batch processing ───────────────────────────────────────

async def test_scan_concurrent_batch_all_processed(tmp_db):
    """15 jobs → processed in 2 batches (10+5) → all 15 in DB."""
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob

    raws = [
        RawJob(source="greenhouse", company=f"Co{i}", title="Eng", url=f"https://x.com/batch/{i}", description="desc")
        for i in range(15)
    ]
    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=7.0))):
        MockGH.return_value.scan = AsyncMock(return_value=raws)
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(side_effect=Exception("no browser"))
        await scan_and_evaluate()
    assert Job.select().count() == 15


# ── apply_jobs: missing scenarios ─────────────────────────────────────────────

async def test_apply_jobs_linkedin_not_easy_apply(tmp_db):
    """LinkedIn job without Easy Apply → warning with manual application message."""
    init_db()
    job = create_job(tmp_db, url="https://www.linkedin.com/jobs/view/li1")
    page = make_mock_page(url="https://www.linkedin.com/jobs/view/li1")
    # query_selector returns None → is_easy_apply() returns False
    page.query_selector = AsyncMock(return_value=None)
    li_applier = LinkedInApplier(page, {}, {})

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier", new=AsyncMock(return_value=li_applier)):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        from candidatador.mcp_server import apply_jobs
        result = await apply_jobs(ids=[job.id])

    assert "Easy Apply" in result or "easy apply" in result.lower()


async def test_apply_jobs_llm_error_still_creates_draft(tmp_db):
    """generate_answers returns draft.error → Application still created in DB."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/err1")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/err1")
    error_draft = ApplicationDraft(job_id=job.id, answers={}, form_fields=[], error="LLM timeout")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.generate_answers", new=AsyncMock(return_value=error_draft)), \
         patch("candidatador.mcp_server._detect_applier") as mock_detect:
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.extract_fields = AsyncMock(return_value=["Q"])
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import apply_jobs
        result = await apply_jobs(ids=[job.id])

    app = Application.get(Application.job == job)
    assert app is not None
    assert "erro" in result.lower() or "Erro" in result or "LLM" in result


async def test_apply_jobs_updates_existing_draft(tmp_db):
    """When Application already exists, form_data is updated (get_or_create → not created path)."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/upd1")
    existing_app = create_application(job, form_data='{"OldQ": "OldA"}')
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/upd1")
    new_draft = ApplicationDraft(job_id=job.id, answers={"NewQ": "NewA"}, form_fields=["NewQ"])

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.generate_answers", new=AsyncMock(return_value=new_draft)), \
         patch("candidatador.mcp_server._detect_applier") as mock_detect:
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.extract_fields = AsyncMock(return_value=["NewQ"])
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import apply_jobs
        await apply_jobs(ids=[job.id])

    app_fresh = Application.get_by_id(existing_app.id)
    data = json.loads(app_fresh.form_data)
    assert "NewQ" in data
    assert data["NewQ"] == "NewA"


async def test_apply_jobs_exception_continues_to_next(tmp_db):
    """Exception inside job processing (from _detect_applier) doesn't abort next job."""
    init_db()
    job1 = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/exc1")
    job2 = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/exc2", company="Linear")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/exc2")
    draft = ApplicationDraft(job_id=job2.id, answers={"Q": "A"}, form_fields=["Q"])

    detect_calls = [0]
    async def detect_side_effect(pg, cfg, prof):
        detect_calls[0] += 1
        if detect_calls[0] == 1:
            raise Exception("ATS detection crashed on job 1")
        mock_applier = AsyncMock()
        mock_applier.extract_fields = AsyncMock(return_value=["Q"])
        return mock_applier

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server.generate_answers", new=AsyncMock(return_value=draft)), \
         patch("candidatador.mcp_server._detect_applier", side_effect=detect_side_effect):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        from candidatador.mcp_server import apply_jobs
        result = await apply_jobs(ids=[job1.id, job2.id])

    # Job 2 should have been processed despite job 1 crashing
    assert Application.select().where(Application.job == job2).count() == 1
    assert "Linear" in result or "exc2" in result


# ── confirm_apply: missing scenarios ──────────────────────────────────────────

async def test_confirm_apply_submit_false_returns_warning(tmp_db, tmp_path):
    """submit() returns False → warning message with screenshot path."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/sf1", status="applying")
    app = create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/sf1")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.fill_form = AsyncMock()
        mock_applier.submit = AsyncMock(return_value="failed")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)

    assert "⚠️" in result or "falhou" in result.lower() or "Submissão" in result
    assert "screenshot" in result.lower() or "04-submitted" in result
    # 'failed' é re-tentável → volta para rascunho
    assert Application.get_by_id(app.id).status == "draft"


async def test_confirm_apply_unverified_marks_submitted_and_warns(tmp_db, tmp_path):
    """RELIABILITY: submit 'unverified' (clicou mas sem confirmação) → registra como
    ENVIADA (não re-submeter, evita duplicar) e avisa para conferir na mão."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/uv1", status="applying")
    app = create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/uv1")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.fill_form = AsyncMock()
        mock_applier.submit = AsyncMock(return_value="unverified")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)

    app_fresh = Application.get_by_id(app.id)
    assert app_fresh.status == "submitted"          # registrada como enviada
    assert app_fresh.email_ref                       # ref de rastreamento gravado
    assert Job.get_by_id(job.id).status == "applied"
    assert "verificar manualmente" in (app_fresh.notes or "")
    assert "04-submitted" in result                  # aponta o screenshot
    assert "retry" in result.lower()                 # avisa para NÃO re-submeter


async def test_confirm_apply_unknown_ats(tmp_db, tmp_path):
    """_detect_applier returns None → ATS não reconhecido."""
    init_db()
    job = create_job(tmp_db, url="https://unknownats.com/jobs/ca99", status="applying")
    create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://unknownats.com/jobs/ca99")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier", new=AsyncMock(return_value=None)), \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        from candidatador.mcp_server import confirm_apply
        result = await confirm_apply(job_id=job.id)

    assert "ATS" in result and "reconhecido" in result


async def test_confirm_apply_linkedin_calls_extract_fields(tmp_db, tmp_path):
    """For LinkedIn jobs, extract_fields() is called to open the modal before fill_form."""
    init_db()
    job = create_job(tmp_db, url="https://www.linkedin.com/jobs/view/ca100", status="applying")
    create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url="https://www.linkedin.com/jobs/view/ca100")

    extract_calls = []

    class TrackingLinkedInApplier(LinkedInApplier):
        async def extract_fields(self):
            extract_calls.append(True)
            return []
        async def fill_form(self, *args, **kwargs):
            pass
        async def submit(self):
            return True

    li_applier = TrackingLinkedInApplier(page, {}, {})

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier", new=AsyncMock(return_value=li_applier)), \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        from candidatador.mcp_server import confirm_apply
        await confirm_apply(job_id=job.id)

    assert len(extract_calls) == 1


# ── get_job: bug fix verification ─────────────────────────────────────────────

async def test_get_job_score_null(tmp_db):
    """get_job with score=None must not raise TypeError (bug fix)."""
    init_db()
    job = create_job(tmp_db, url="https://x.com/gj-null-score", score=None)
    from candidatador.mcp_server import get_job
    result = await get_job(id=job.id)
    assert "—" in result
    assert "não encontrada" not in result


# ── login ─────────────────────────────────────────────────────────────────────

async def test_login_unsupported_platform(tmp_db):
    """login() with unsupported platform returns error message."""
    init_db()
    from candidatador.mcp_server import login
    result = await login(platform="github")
    assert "not supported" in result or "suport" in result.lower() or "github" in result.lower()


async def test_login_linkedin_returns_instruction(tmp_db):
    """login('linkedin') opens browser and returns instruction string."""
    init_db()
    page = make_mock_page(url="https://www.linkedin.com/login")
    with patch("candidatador.mcp_server._browser_mod") as mock_browser:
        mock_browser.new_page = AsyncMock(return_value=page)
        from candidatador.mcp_server import login
        result = await login(platform="linkedin")
    assert "linkedin" in result.lower()
    page.goto.assert_called_once()


# ── list_jobs: table formatting ───────────────────────────────────────────────

async def test_list_jobs_salary_estimate_shows_asterisk(tmp_db):
    """salary_source='llm_estimate' with min+max → '* ' appears in table."""
    init_db()
    create_job(tmp_db, url="https://x.com/lj-est",
               salary_min=150000, salary_max=200000,
               salary_currency="USD", salary_source="llm_estimate", status="new")
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="new")
    assert " *" in result


async def test_list_jobs_salary_min_only_shows_plus(tmp_db):
    """Only salary_min set → '$Xk+' format in table."""
    init_db()
    create_job(tmp_db, url="https://x.com/lj-min",
               salary_min=120000, salary_max=None,
               salary_currency="USD", salary_source="stated", status="new")
    from candidatador.mcp_server import list_jobs
    result = await list_jobs(status="new")
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
    from candidatador.mcp_server import get_pipeline
    result = await get_pipeline()
    assert "3" in result


# ── validate_startup integration ──────────────────────────────────────────────

def test_validate_startup_called_at_import_with_real_config():
    """validate_startup não lança exceção durante inicialização do mcp_server."""
    # O mcp_server já foi importado nos testes anteriores.
    # Este teste garante que o módulo importa sem crash mesmo sem API key.
    import candidatador.mcp_server  # noqa: F401 — verifica que importa ok
    assert True  # se chegou aqui, não crashou


def test_startup_warning_level_values():
    from candidatador.startup import StartupWarning
    w_err = StartupWarning(level="error", message="msg")
    w_warn = StartupWarning(level="warn", message="msg")
    assert w_err.level == "error"
    assert w_warn.level == "warn"


# ── LinkedIn session expired warning ──────────────────────────────────────────

async def test_scan_linkedin_session_expired_shows_warning(tmp_db):
    """LinkedInSessionExpiredError → aviso explícito no resultado (não silêncio)."""
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.playwright_sources import LinkedInSessionExpiredError

    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.scanner.playwright_sources.LinkedInScanner") as MockLI:
        MockGH.return_value.scan = AsyncMock(return_value=[])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        MockLI.return_value.scan = AsyncMock(
            side_effect=LinkedInSessionExpiredError("Sessão expirada.")
        )
        result = await scan_and_evaluate()

    assert "LinkedIn" in result
    assert "expirada" in result or "login" in result.lower()


async def test_scan_linkedin_session_expired_does_not_block_http_results(tmp_db):
    """LinkedInSessionExpiredError não impede que vagas HTTP sejam retornadas."""
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob
    from candidatador.scanner.playwright_sources import LinkedInSessionExpiredError

    raw = RawJob(source="greenhouse", company="Stripe", title="Eng", url="https://x.com/li-exp-1", description="desc")

    with patch("candidatador.mcp_server.GreenhouseScanner") as MockGH, \
         patch("candidatador.mcp_server.LeverScanner") as MockLV, \
         patch("candidatador.mcp_server.AshbyScanner") as MockAB, \
         patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.scanner.playwright_sources.LinkedInScanner") as MockLI, \
         patch("candidatador.mcp_server.evaluate_job", new=AsyncMock(return_value=make_eval_result(score=8.0))):
        MockGH.return_value.scan = AsyncMock(return_value=[raw])
        MockLV.return_value.scan = AsyncMock(return_value=[])
        MockAB.return_value.scan = AsyncMock(return_value=[])
        mock_browser.new_page = AsyncMock(return_value=make_mock_page())
        MockLI.return_value.scan = AsyncMock(
            side_effect=LinkedInSessionExpiredError("Sessão expirada.")
        )
        result = await scan_and_evaluate()

    assert "Stripe" in result  # vaga HTTP aparece
    assert "LinkedIn" in result  # aviso aparece também


# ── email: _build_email_alias ─────────────────────────────────────────────────

def test_build_email_alias_formats_correctly():
    from candidatador.mcp_server import _build_email_alias
    result = _build_email_alias("candidaturas@gmail.com", "x7k2mp")
    assert result == "candidaturas+x7k2mp@gmail.com"


def test_build_email_alias_different_refs():
    from candidatador.mcp_server import _build_email_alias
    assert _build_email_alias("a@b.com", "abc") == "a+abc@b.com"
    assert _build_email_alias("a@b.com", "xyz") == "a+xyz@b.com"


# ── email: confirm_apply gera ref e salva ─────────────────────────────────────

async def test_confirm_apply_generates_6_char_ref(tmp_db, tmp_path):
    """confirm_apply deve gerar um email_ref com 6 caracteres e persistir."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca-ref-1", status="applying")
    app = create_application(job, status="draft", form_data='{"Q": "A"}')
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url=job.url)

    from candidatador.mcp_server import confirm_apply
    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        applier = AsyncMock()
        applier.fill_form = AsyncMock()
        applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = applier
        await confirm_apply(job_id=job.id)

    saved = Application.get_by_id(app.id)
    assert saved.email_ref is not None
    assert len(saved.email_ref) == 6


async def test_confirm_apply_ref_is_url_safe(tmp_db, tmp_path):
    """O ref gerado deve conter apenas chars url-safe (letras, dígitos, -, _)."""
    import re
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/ca-safe-1", status="applying")
    app = create_application(job, status="draft", form_data='{"Q": "A"}')
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    page = make_mock_page(url=job.url)

    from candidatador.mcp_server import confirm_apply
    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        applier = AsyncMock()
        applier.fill_form = AsyncMock()
        applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = applier
        await confirm_apply(job_id=job.id)

    saved = Application.get_by_id(app.id)
    assert re.match(r'^[A-Za-z0-9_-]{6}$', saved.email_ref)


async def test_confirm_apply_refs_are_unique_across_calls(tmp_db, tmp_path):
    """Dez chamadas a confirm_apply devem gerar refs distintos."""
    init_db()
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake pdf")
    refs = set()

    from candidatador.mcp_server import confirm_apply
    for i in range(10):
        job = create_job(tmp_db,
                         url=f"https://boards.greenhouse.io/stripe/jobs/uniq-{i}",
                         status="applying")
        create_application(job, status="draft", form_data='{"Q": "A"}')
        page = make_mock_page(url=job.url)

        with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
             patch("candidatador.mcp_server._detect_applier") as mock_detect, \
             patch("candidatador.mcp_server.os.path.exists", return_value=True), \
             patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
             patch("candidatador.mcp_server.os.path.dirname"), \
             patch("candidatador.mcp_server.os.path.abspath"):
            mock_browser.new_page = AsyncMock(return_value=page)
            mock_browser.save_screenshot = AsyncMock()
            applier = AsyncMock()
            applier.fill_form = AsyncMock()
            applier.submit = AsyncMock(return_value="submitted")
            mock_detect.return_value = applier
            await confirm_apply(job_id=job.id)

        refs.add(Application.get(Application.job == job).email_ref)

    # Com 10 refs de 6 chars urlsafe (~62^6 possibilidades), colisão é virtualmente zero
    assert len(refs) == 10


# ── email: setup_email MCP tool ───────────────────────────────────────────────

async def test_setup_email_calls_gmail_flow():
    """setup_email deve iniciar o fluxo OAuth e confirmar sucesso."""
    from candidatador.mcp_server import setup_email
    with patch("candidatador.mcp_server.setup_gmail_service") as mock_setup, \
         patch("candidatador.mcp_server.load_config", return_value={
             "email": {
                 "address": "candidaturas@gmail.com",
                 "credentials_path": "~/.candidatador/gmail-client.json",
                 "token_path": "~/.candidatador/gmail-token.json",
             }
         }), \
         patch("candidatador.mcp_server._run_gmail_oauth") as mock_oauth, \
         patch("os.path.exists", return_value=True):
        mock_oauth.return_value = None
        mock_setup.return_value = MagicMock()
        result = await setup_email()

    assert "sucesso" in result.lower() or "configurad" in result.lower()


async def test_setup_email_raises_friendly_error_when_client_json_missing():
    """setup_email deve retornar mensagem clara se gmail-client.json não existe."""
    from candidatador.mcp_server import setup_email
    with patch("candidatador.mcp_server.load_config", return_value={
        "email": {
            "address": "candidaturas@gmail.com",
            "credentials_path": "/nonexistent/gmail-client.json",
            "token_path": "~/.candidatador/gmail-token.json",
        }
    }):
        result = await setup_email()

    assert "client" in result.lower() or "credential" in result.lower() or "erro" in result.lower()


# ── email: sync_email_responses MCP tool ─────────────────────────────────────

async def test_sync_email_responses_returns_summary(tmp_db):
    """sync_email_responses deve chamar sync_responses e retornar resumo legível."""
    init_db()
    from candidatador.mcp_server import sync_email_responses

    fake_updates = [
        {"company": "Anthropic", "title": "Senior Engineer",
         "type": "interview", "stage": "technical_interview",
         "match_type": "ref"},
        {"company": "Stripe", "title": "Backend Eng",
         "type": "rejection", "stage": None,
         "match_type": "fuzzy"},
    ]

    with patch("candidatador.mcp_server.sync_responses",
               new=AsyncMock(return_value=fake_updates)), \
         patch("candidatador.mcp_server.load_config", return_value={
             "email": {
                 "address": "candidaturas@gmail.com",
                 "credentials_path": "~/.candidatador/gmail-client.json",
                 "token_path": "~/.candidatador/gmail-token.json",
                 "processed_label": "candidatador/processado",
                 "interview_stages": [],
             },
             "llm_model": "claude-sonnet-4-6",
         }):
        result = await sync_email_responses()

    assert "Anthropic" in result
    assert "Stripe" in result
    assert "2" in result or "dois" in result.lower() or len(result) > 10


async def test_sync_email_responses_empty_inbox(tmp_db):
    """sync_email_responses com inbox vazia deve retornar mensagem adequada."""
    init_db()
    from candidatador.mcp_server import sync_email_responses

    with patch("candidatador.mcp_server.sync_responses",
               new=AsyncMock(return_value=[])), \
         patch("candidatador.mcp_server.load_config", return_value={
             "email": {
                 "address": "candidaturas@gmail.com",
                 "credentials_path": "~/.candidatador/gmail-client.json",
                 "token_path": "~/.candidatador/gmail-token.json",
                 "processed_label": "candidatador/processado",
                 "interview_stages": [],
             },
             "llm_model": "claude-sonnet-4-6",
         }):
        result = await sync_email_responses()

    assert "nenhum" in result.lower() or "0" in result or "vazio" in result.lower()


def test_mcp_server_initializes_logging():
    """Importar o mcp_server não deve explodir e deve ter setup de logging configurado."""
    import candidatador.log as log_mod
    # se o módulo já foi importado, _initialized deve ser True
    assert log_mod._initialized is True


# ── _archive_screenshots ──────────────────────────────────────────────────────

def test_archive_screenshots_moves_dir(tmp_path):
    """_archive_screenshots move o dir de screenshots para done/<job_id>/."""
    from candidatador.mcp_server import _archive_screenshots

    job_dir = tmp_path / "42"
    job_dir.mkdir()
    (job_dir / "01-job-page.png").write_bytes(b"img")
    (job_dir / "04-submitted.png").write_bytes(b"img")

    config = {"screenshots_dir": str(tmp_path)}
    _archive_screenshots(42, config)

    assert not job_dir.exists()
    done_dir = tmp_path / "done" / "42"
    assert done_dir.exists()
    assert (done_dir / "04-submitted.png").exists()


def test_archive_screenshots_no_dir_is_noop(tmp_path):
    """_archive_screenshots não falha quando o dir ainda não existe."""
    from candidatador.mcp_server import _archive_screenshots
    config = {"screenshots_dir": str(tmp_path)}
    _archive_screenshots(999, config)  # não deve levantar


def test_archive_screenshots_overwrites_existing_done(tmp_path):
    """_archive_screenshots substitui done/<job_id>/ se já existe."""
    from candidatador.mcp_server import _archive_screenshots

    job_dir = tmp_path / "7"
    job_dir.mkdir()
    (job_dir / "new.png").write_bytes(b"new")

    done_dir = tmp_path / "done" / "7"
    done_dir.mkdir(parents=True)
    (done_dir / "old.png").write_bytes(b"old")

    config = {"screenshots_dir": str(tmp_path)}
    _archive_screenshots(7, config)

    assert (done_dir / "new.png").exists()
    assert not (done_dir / "old.png").exists()


async def test_confirm_apply_archives_on_success(tmp_db, tmp_path):
    """confirm_apply chama _archive_screenshots quando outcome='submitted'."""
    init_db()
    job = create_job(tmp_db, url="https://boards.greenhouse.io/stripe/jobs/arch1", status="applying")
    create_application(job)
    cv_path = tmp_path / "cv.pdf"
    cv_path.write_bytes(b"fake")
    page = make_mock_page(url="https://boards.greenhouse.io/stripe/jobs/arch1")

    with patch("candidatador.mcp_server._browser_mod") as mock_browser, \
         patch("candidatador.mcp_server._detect_applier") as mock_detect, \
         patch("candidatador.mcp_server.os.path.exists", return_value=True), \
         patch("candidatador.mcp_server.os.path.join", return_value=str(cv_path)), \
         patch("candidatador.mcp_server.os.path.dirname"), \
         patch("candidatador.mcp_server.os.path.abspath"), \
         patch("candidatador.mcp_server._archive_screenshots") as mock_archive:
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        mock_applier = AsyncMock()
        mock_applier.fill_form = AsyncMock()
        mock_applier.submit = AsyncMock(return_value="submitted")
        mock_detect.return_value = mock_applier
        from candidatador.mcp_server import confirm_apply
        await confirm_apply(job_id=job.id)

    mock_archive.assert_called_once_with(job.id, mock_archive.call_args[0][1])


# ── scan race condition (duplicate LLM calls) ─────────────────────────────────

def _scan_patches(raw_jobs, eval_mock):
    """Context manager stack shared by race condition tests."""
    from unittest.mock import patch, AsyncMock
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("candidatador.mcp_server.GreenhouseScanner",
        **{"return_value.scan": AsyncMock(return_value=raw_jobs)}))
    stack.enter_context(patch("candidatador.mcp_server.LeverScanner",
        **{"return_value.scan": AsyncMock(return_value=[])}))
    stack.enter_context(patch("candidatador.mcp_server.AshbyScanner",
        **{"return_value.scan": AsyncMock(return_value=[])}))
    stack.enter_context(patch("candidatador.mcp_server._browser_mod",
        **{"new_page": AsyncMock(side_effect=Exception("no browser"))}))
    stack.enter_context(patch("candidatador.mcp_server.evaluate_job", new=eval_mock))
    return stack


async def test_scan_concurrent_calls_evaluate_same_url_only_once(tmp_db):
    """Concurrent scan_and_evaluate calls must not call evaluate_job twice for the same URL.

    Reproduces the race condition where 11 parallel MCP tool invocations each saw
    the same empty ScanLog snapshot and fired 11 LLM calls per job.
    """
    import asyncio
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob

    url = "https://x.com/race-1"
    raw = RawJob(source="greenhouse", company="Co", title="Eng", url=url, description="desc")
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        # Fire 5 concurrent scans for the same job
        await asyncio.gather(*[scan_and_evaluate() for _ in range(5)])

    # LLM must have been called exactly once despite 5 concurrent scans
    assert eval_mock.call_count == 1
    # Exactly one Job and one ScanLog entry
    assert Job.select().where(Job.url == url).count() == 1
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 1


async def test_scan_spend_limit_releases_scan_log_claim(tmp_db):
    """When evaluate_job raises (spend limit), the ScanLog claim is released
    so the URL can be retried on the next scan."""
    init_db()
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob

    url = "https://x.com/spend-limit-1"
    raw = RawJob(source="greenhouse", company="Co", title="Eng", url=url, description="desc")
    spend_limit_err = Exception("claude CLI exited with code 1: You've hit your monthly spend limit")
    failing_eval = AsyncMock(side_effect=spend_limit_err)

    with _scan_patches([raw], failing_eval):
        with pytest.raises(Exception, match="spend limit"):
            await scan_and_evaluate()

    # Claim must be released — ScanLog should be empty so next scan retries the URL
    assert ScanLog.select().where(ScanLog.job_url == url).count() == 0
    # No Job was created
    assert Job.select().where(Job.url == url).count() == 0


async def test_scan_already_in_scan_log_skips_llm(tmp_db):
    """URL already in ScanLog at scan start → evaluate_job not called (existing dedup)."""
    init_db()
    ScanLog.create(job_url="https://x.com/already-seen", source="greenhouse")
    from candidatador.mcp_server import scan_and_evaluate
    from candidatador.scanner.base import RawJob

    raw = RawJob(source="greenhouse", company="Co", title="Eng", url="https://x.com/already-seen")
    eval_mock = AsyncMock(return_value=make_eval_result(score=8.0))

    with _scan_patches([raw], eval_mock):
        await scan_and_evaluate()

    eval_mock.assert_not_called()

