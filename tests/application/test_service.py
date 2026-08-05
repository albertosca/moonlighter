"""Unit tests for apply_service: detect_applier (real loop, no mock),
archive_screenshots (early-return and swallowed exception), and the
apply_jobs/confirm_apply branches that test_mcp_server's happy path doesn't touch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from moonlighter.application import service as apply_service
from moonlighter.application.answers.cv import CVNotFoundError
from moonlighter.application.appliers.base import ApplicationDraft, BaseApplier
from moonlighter.application.appliers.greenhouse import GreenhouseApplier
from moonlighter.application.appliers.recruitee import RecruiteeApplier
from moonlighter.application.appliers.smartrecruiters import SmartRecruitersApplier
from moonlighter.application.appliers.workable import WorkableApplier
from moonlighter.application.service import _anomaly_reasons, _render_draft
from moonlighter.core.db import Application, Job, init_db
from playwright.async_api import TimeoutError as PlaywrightTimeout

from tests._context import make_applier_mock

CONFIG = {"screenshots_dir": "/tmp/moonlighter-test-shots", "llm_model": "x", "email": {}}
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


# ── page_session ─────────────────────────────────────────────────────────────


async def test_page_session_closes_on_error():
    from moonlighter.application.service import page_session

    fake_page = AsyncMock()
    with (
        patch(
            "moonlighter.application.service.browser.new_page", AsyncMock(return_value=fake_page)
        ),
        pytest.raises(RuntimeError),
    ):
        async with page_session({}) as p:
            assert p is fake_page
            raise RuntimeError("boom")
    fake_page.close.assert_awaited_once()


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


async def test_detect_applier_matches_recruitee(tmp_db):
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://acme.recruitee.com/o/backend-engineer"), CONFIG, PROFILE
    )
    assert isinstance(applier, RecruiteeApplier)


async def test_detect_applier_matches_workable(tmp_db):
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://apply.workable.com/acme/j/ABCDEF1234/apply/"), CONFIG, PROFILE
    )
    assert isinstance(applier, WorkableApplier)


async def test_detect_applier_returns_none_for_linkedin_when_no_plugin_installed(tmp_db):
    """Steady state for the public repo alone: nothing is registered under
    moonlighter.appliers for LinkedIn (it moved to the private moonlighter-linkedin
    plugin -- see docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md),
    so detect_applier finds no match for a linkedin.com URL."""
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://www.linkedin.com/jobs/view/12345"), CONFIG, PROFILE
    )
    assert applier is None


class _FakePluginApplier(BaseApplier):
    async def detect(self):
        return "example-ats.test" in self.page.url

    async def extract_fields(self):
        return ([], frozenset())

    async def fill_form(self, answers, cv_path):
        return {}

    async def submit(self):
        return "submitted"


async def test_detect_applier_matches_a_registered_plugin(tmp_db):
    """A class discovered via the moonlighter.appliers entry_points group (appended
    to _APPLIER_CLASSES once at import time -- see service.py) is detected
    generically -- proves the plugin path itself works, without needing the real
    LinkedIn plugin installed."""
    init_db()
    with patch(
        "moonlighter.application.service._APPLIER_CLASSES",
        [*apply_service._APPLIER_CLASSES, _FakePluginApplier],
    ):
        applier = await apply_service.detect_applier(
            _page("https://example-ats.test/jobs/1"), CONFIG, PROFILE
        )
    assert isinstance(applier, _FakePluginApplier)


async def test_detect_applier_matches_smartrecruiters(tmp_db):
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://jobs.smartrecruiters.com/oneclick-ui/company/Acme/publication/abc"),
        CONFIG,
        PROFILE,
    )
    assert isinstance(applier, SmartRecruitersApplier)


async def test_detect_applier_source_routes_recruitee_custom_domain(tmp_db):
    """Most real Recruitee companies use a custom career domain (not *.recruitee.com),
    so the URL-only check in RecruiteeApplier.detect() would never match. Passing
    the scanner-known source must route to RecruiteeApplier anyway, without relying
    on the URL at all. This fails against the old (source-less) detect_applier,
    which falls through the URL loop and returns None for this non-recruitee.com
    domain."""
    applier = await apply_service.detect_applier(
        _page("https://jobs.channable.com/o/backend-engineer"),
        CONFIG,
        PROFILE,
        source="recruitee",
    )
    assert isinstance(applier, RecruiteeApplier)


async def test_detect_applier_source_greenhouse_falls_back_to_url(tmp_db):
    """A greenhouse job has no applier whose SOURCE == 'greenhouse', so the
    source-first pass finds nothing and the existing URL-based loop still applies."""
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://boards.greenhouse.io/stripe/jobs/1"),
        CONFIG,
        PROFILE,
        source="greenhouse",
    )
    assert isinstance(applier, GreenhouseApplier)


async def test_detect_applier_no_source_uses_url_loop_unchanged(tmp_db):
    """Backward compat: source=None (the default) runs exactly the pre-existing
    URL-based detection loop."""
    init_db()
    applier = await apply_service.detect_applier(
        _page("https://acme.recruitee.com/o/backend-engineer"), CONFIG, PROFILE
    )
    assert isinstance(applier, RecruiteeApplier)


# ── archive_screenshots ─────────────────────────────────────────────────────


def test_archive_screenshots_noop_when_missing(tmp_path):
    # src doesn't exist → returns without error
    apply_service.archive_screenshots(123, {"screenshots_dir": str(tmp_path)})


def test_archive_screenshots_swallows_exception(tmp_path):
    src = tmp_path / "456"
    src.mkdir()
    with patch("moonlighter.application.service.shutil.move", side_effect=OSError("disk")):
        # exception is logged as non-critical, does not propagate
        apply_service.archive_screenshots(456, {"screenshots_dir": str(tmp_path)})


# ── apply_jobs: needs_review block ───────────────────────────────────────────


async def test_apply_jobs_shows_needs_review_fields(tmp_db):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nr")
    draft = ApplicationDraft(
        job_id=job.id,
        answers={"Work auth?": "__NEEDS_REVIEW__", "Name": "Alberto"},
        form_fields=["Work auth?", "Name"],
    )
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.generate_answers",
            new=AsyncMock(return_value=draft),
        ),
        patch("moonlighter.application.service.detect_applier") as mock_detect,
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.save_screenshot = AsyncMock()
        applier = make_applier_mock()
        applier.extract_fields = AsyncMock(return_value=(["Work auth?", "Name"], frozenset()))
        mock_detect.return_value = applier
        result = await apply_service.apply_jobs([job.id], CONFIG, PROFILE, MagicMock())
    assert "NEED YOUR DECISION" in result
    assert "Work auth?" in result
    # NEEDS_REVIEW field is not rendered as a normal answer, but Name is
    assert "Alberto" in result


async def test_apply_jobs_survives_networkidle_timeout_on_spa_with_persistent_traffic(tmp_db):
    """SPA-heavy ATS pages (Recruitee, Workable, ...) often keep a background
    connection open (chat widget, analytics beacon) so Playwright's networkidle
    never fires even though the page finished loading and is fully usable — see
    the live Ziflow/Recruitee repro. goto() succeeding is the real load signal;
    a networkidle timeout on top of that must not abort the whole draft."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/idle")
    draft = ApplicationDraft(job_id=job.id, answers={"Name": "Alberto"}, form_fields=["Name"])
    page = _page(job.url)
    page.wait_for_load_state = AsyncMock(side_effect=PlaywrightTimeout("Timeout 15000ms exceeded."))
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.generate_answers",
            new=AsyncMock(return_value=draft),
        ),
        patch("moonlighter.application.service.detect_applier") as mock_detect,
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.save_screenshot = AsyncMock()
        applier = make_applier_mock()
        applier.extract_fields = AsyncMock(return_value=(["Name"], frozenset()))
        mock_detect.return_value = applier
        result = await apply_service.apply_jobs([job.id], CONFIG, PROFILE, MagicMock())
    assert "error" not in result.lower()
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


def test_anomaly_closed_set_answer_never_flagged_for_length():
    """A long-but-legitimate closed-set option (e.g. a verbose language-level
    dropdown label) must not be flagged just because it's longer than short
    free-text peers."""
    others = ["short one", "short two", "short three"]
    long_but_closed_set = (
        "Fluent/Native — I can work fully in English with no communication barriers"
    )
    reasons = apply_service._anomaly_reasons(long_but_closed_set, others, is_closed_set=True)
    assert "disproportionately long" not in " ".join(reasons)


def test_anomaly_closed_set_answer_still_flagged_for_url():
    """is_closed_set only silences the length heuristic — URL/email/phone
    checks still run."""
    reasons = apply_service._anomaly_reasons("see https://evil.test/x", [], is_closed_set=True)
    assert any("URL" in r for r in reasons)


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


def test_render_draft_excludes_closed_set_peers_from_median_and_never_flags_them(tmp_db):
    """Reproduces the live Ziflow false-positive: several short boolean
    closed-set answers (radio Yes/No) must not drag the peer median down
    and cause a normal-length free-text answer to be flagged, AND the
    closed-set answers themselves must never be flagged for length."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/closedset")
    draft = ApplicationDraft(
        job_id=job.id,
        answers={
            "Full name": "Alberto Albuquerque",
            "Beginner (A1-A2)": "No",
            "Intermediate (B1)": "No",
            "Advanced (C1)": "No",
            "Native (C2)": "Yes",
        },
        form_fields=[
            "Full name",
            "Beginner (A1-A2)",
            "Intermediate (B1)",
            "Advanced (C1)",
            "Native (C2)",
        ],
        closed_set_fields=frozenset(
            {"Beginner (A1-A2)", "Intermediate (B1)", "Advanced (C1)", "Native (C2)"}
        ),
    )
    result = _render_draft(job.id, job, draft)
    assert "Full name" not in _extract_flagged_fields(result)


def _extract_flagged_fields(rendered: str) -> list[str]:
    """Pulls the flagged field names out of the '⚠️ REVIEW CAREFULLY' block,
    if present — used by the regression test above."""
    if "REVIEW CAREFULLY" not in rendered:
        return []
    block = rendered.split("REVIEW CAREFULLY", 1)[1]
    return [line.split("**")[1] for line in block.splitlines() if line.strip().startswith("- **")]


# ── confirm_apply: branches ─────────────────────────────────────────────────


def _confirm_mocks(job, *, fill_status, submit="submitted"):
    applier = AsyncMock()
    applier.fill_form = AsyncMock(return_value=fill_status)
    applier.submit = AsyncMock(return_value=submit)
    return applier


async def test_confirm_apply_without_email_config_skips_alias(tmp_db, tmp_path):
    """config with no email.address → does not inject alias (false branch of `if base_address`)."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/noemail")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x"}  # no "email" key
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submitted and confirmed" in result


async def test_confirm_apply_logs_failed_fields_but_submits(tmp_db, tmp_path):
    """Fields that fail to fill generate a warning but don't prevent a confirmed submit."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/partial")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto", "X": "y"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled", "X": "failed:not_found"})
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submitted and confirmed" in result
    assert Application.get(Application.job == job).status == "submitted"


# ── _fill_open_page ─────────────────────────────────────────────────────────


async def test_fill_open_page_fills_and_screenshots_without_submit(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/fop")
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
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
    page.close.assert_not_called()  # the helper does NOT close the page
    mock_browser.save_screenshot.assert_awaited()  # screenshot 03 tirado


async def test_fill_open_page_calls_prepare_hook(tmp_db, tmp_path):
    """_fill_open_page calls applier.prepare() unconditionally -- for an applier
    that overrides it (like LinkedIn), this is where the Easy-Apply-modal side
    effect happens. For every other applier (default no-op), this is a no-op."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/acme/jobs/1")
    page = _page(job.url)
    applier = make_applier_mock(MagicMock())
    applier.extract_fields = AsyncMock(return_value=(["Field"], frozenset()))
    applier.fill_form = AsyncMock(return_value={"Field": "filled"})

    with (
        patch(
            "moonlighter.application.service.detect_applier",
            new=AsyncMock(return_value=applier),
        ),
        patch("moonlighter.application.service.browser") as mock_browser,
    ):
        mock_browser.save_screenshot = AsyncMock()
        await apply_service._fill_open_page(page, job, {"Field": "value"}, "", CONFIG, PROFILE)

    applier.prepare.assert_called_once()


async def test_fill_open_page_survives_networkidle_timeout_on_spa_with_persistent_traffic(
    tmp_db, tmp_path
):
    """Same networkidle unreliability as apply_jobs (see the sibling test in
    _draft_one) — _fill_open_page is a separate call site with the same pattern
    and needs the same tolerance."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/fop-idle")
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    page.wait_for_load_state = AsyncMock(side_effect=PlaywrightTimeout("Timeout 15000ms exceeded."))
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
    ):
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service._fill_open_page(
            page, job, {"Name": "Alberto"}, "/tmp/cv.pdf", cfg, PROFILE
        )
    assert result is not None
    _, fill_status = result
    assert fill_status == {"Name": "filled"}


async def test_fill_open_page_returns_none_for_unknown_ats(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://unknown/jobs/1")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch("moonlighter.application.service.detect_applier", new=AsyncMock(return_value=None)),
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
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "FILLED" in result
    assert "submit_application" in result
    assert str(tmp_path) in result  # screenshot path derives from screenshots_dir, not hardcoded
    applier.submit.assert_not_called()  # does NOT submit
    saved = Application.get(Application.job == job)
    assert saved.status == "filled"
    assert saved.email_ref is not None  # ref persisted
    page.close.assert_awaited_once()  # no failure => closes normally


async def test_fill_application_blocks_on_needs_review(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nr2")
    Application.create(job=job, status="draft", form_data='{"Work auth?": "__NEEDS_REVIEW__"}')
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "NOT submitted" in result or "awaiting your decision" in result
    assert Application.get(Application.job == job).status == "draft"  # did not become filled


async def test_fill_application_aborts_on_missing_cv(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nocv")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with patch(
        "moonlighter.application.service.resolve_cv_path",
        side_effect=CVNotFoundError("cv.pdf does not exist"),
    ):
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "Not filled" in result


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
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "failed" in result.lower() and "X" in result
    mock_browser.hide_window.assert_awaited_once()
    mock_browser.show_window.assert_awaited_once()
    page.close.assert_not_awaited()  # aba fica aberta pro humano mexer


async def test_fill_application_no_draft(tmp_db, tmp_path):
    init_db()
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.fill_application(99999, None, cfg, PROFILE)
    assert "not found" in result


async def test_fill_application_unknown_ats(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://unknown/jobs/2")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch("moonlighter.application.service.detect_applier", new=AsyncMock(return_value=None)),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "ATS not recognized" in result
    page.close.assert_awaited_once()  # unknown ATS doesn't need human help


async def test_fill_application_handles_exception(tmp_db, tmp_path):
    """An unexpected error in _fill_open_page is captured and returned as a warning message."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/exc")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    page = _page(job.url)
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service._fill_open_page",
            new=AsyncMock(side_effect=RuntimeError("unexpected failure")),
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.fill_application(job.id, None, cfg, PROFILE)
    assert "Error filling" in result
    assert "unexpected failure" in result
    page.close.assert_not_awaited()  # aba fica aberta pro humano mexer
    mock_browser.show_window.assert_awaited_once()


async def test_confirm_apply_survives_hide_window_failure(tmp_db, tmp_path):
    """hide_window (best-effort) raising before the try must not tear down the flow nor
    prevent the submit — the page keeps being used and is closed normally."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/hidefail")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"})
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        page = _page(job.url)
        mock_browser.new_page = AsyncMock(return_value=page)
        mock_browser.hide_window = AsyncMock(side_effect=RuntimeError("cdp down"))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "submitted and confirmed" in result
    page.close.assert_awaited_once()


async def test_confirm_apply_survives_show_window_failure_on_exception(tmp_db, tmp_path):
    """If show_window (best-effort) raises inside _submit_on_page's generic exception
    handler, the CDP error must not mask the original error nor skip the state
    revert — confirm_apply still returns the friendly message and reverts app/job."""
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/cdpdown")
    Application.create(job=job, status="draft", form_data='{"Name": "Alberto"}')
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service._fill_open_page",
            new=AsyncMock(side_effect=RuntimeError("unexpected failure")),
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock(side_effect=RuntimeError("cdp down"))
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.confirm_apply(job.id, None, cfg, PROFILE)
    assert "Error submitting" in result
    assert "unexpected failure" in result
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
    assert Application.get(Application.job == job).status == "draft"  # did not submit


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
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        result = await apply_service.submit_application(job.id, cfg, PROFILE)
    assert "submitted and confirmed" in result
    applier.submit.assert_awaited()
    assert Application.get(Application.job == job).status == "submitted"


async def test_submit_application_no_draft(tmp_db, tmp_path):
    init_db()
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    result = await apply_service.submit_application(99999, cfg, PROFILE)
    assert "not found" in result


async def test_submit_application_missing_cv(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/subnocv")
    Application.create(job=job, status="filled", form_data='{"Name": "Alberto"}', email_ref="r")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    with patch(
        "moonlighter.application.service.resolve_cv_path",
        side_effect=CVNotFoundError("cv.pdf does not exist"),
    ):
        result = await apply_service.submit_application(job.id, cfg, PROFILE)
    assert "Not submitted" in result


async def test_submit_stops_and_detaches_when_a_captcha_guards_the_form(tmp_db, tmp_path):
    """A captcha token minted in an automated tab is rejected server-side —
    Recruitee answers HTTP 422 on captchaToken, which the generic classifier
    reports as failed:validation_errors:[] with no field at fault. Clicking is
    therefore never right: stop, hand the window over, and let go of the browser
    so the human's captcha is solved in a page nobody is driving."""
    init_db()
    job = _job(url="https://acme.recruitee.com/o/eng/c/new")
    Application.create(job=job, status="filled", form_data='{"Name": "Alberto"}', email_ref="r1")
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"}, submit="submitted")

    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
        patch(
            "moonlighter.application.service.detect_captcha",
            new=AsyncMock(return_value="hcaptcha"),
        ),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.show_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        mock_browser.detach = AsyncMock()
        result = await apply_service.submit_application(job.id, cfg, PROFILE)

    applier.submit.assert_not_awaited()
    mock_browser.detach.assert_awaited_once()
    mock_browser.show_window.assert_awaited()
    assert "hcaptcha" in result
    assert "NOT submitted" in result
    app = Application.get(Application.job == job)
    assert app.status == "needs_review"
    assert app.applied_at is None
    assert "captcha" in app.notes


async def test_submit_proceeds_normally_when_there_is_no_captcha(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://boards.greenhouse.io/stripe/jobs/nocap")
    Application.create(job=job, status="filled", form_data='{"Name": "Alberto"}', email_ref="n1")
    cv = tmp_path / "cv.pdf"
    cv.write_text("x")
    cfg = {"screenshots_dir": str(tmp_path), "llm_model": "x", "email": {}}
    applier = _confirm_mocks(job, fill_status={"Name": "filled"}, submit="submitted")

    with (
        patch("moonlighter.application.service.browser") as mock_browser,
        patch(
            "moonlighter.application.service.detect_applier", new=AsyncMock(return_value=applier)
        ),
        patch("moonlighter.application.service.resolve_cv_path", return_value=str(cv)),
        patch("moonlighter.application.service.detect_captcha", new=AsyncMock(return_value=None)),
    ):
        mock_browser.new_page = AsyncMock(return_value=_page(job.url))
        mock_browser.hide_window = AsyncMock()
        mock_browser.save_screenshot = AsyncMock()
        mock_browser.detach = AsyncMock()
        result = await apply_service.submit_application(job.id, cfg, PROFILE)

    applier.submit.assert_awaited()
    mock_browser.detach.assert_not_awaited()
    assert "submitted and confirmed" in result


def test_render_filled_prints_every_answer_in_full(tmp_db):
    init_db()
    """The screenshot shows a scrolled slice of each textarea, so approving from
    it alone means approving text nobody read. The answers are already persisted;
    surfacing them is what makes the review real rather than a formality."""
    job = _job(url="https://acme.recruitee.com/o/eng")
    longa = "First paragraph.\n\nSecond paragraph that runs well past any textarea. " * 6
    answers = {
        "Full name": "Alberto",
        "Why do you want this?": longa,
        "CV or resume": "[FILE UPLOAD]",
    }
    out = apply_service._render_filled(
        job,
        {"Full name": "filled", "Why do you want this?": "filled"},
        {"screenshots_dir": "/t"},
        answers,
    )

    assert longa.strip() in out, "a resposta longa precisa sair inteira, sem corte"
    assert "Why do you want this?" in out
    assert "Alberto" in out


def test_render_filled_marks_fields_that_failed(tmp_db, tmp_path):
    init_db()
    job = _job(url="https://acme.recruitee.com/o/eng2")
    out = apply_service._render_filled(
        job,
        {"Salary": "failed:number_field_needs_digits_only"},
        {"screenshots_dir": str(tmp_path)},
        {"Salary": "USD 110,000 per year"},
    )
    assert "Salary" in out
    assert "number_field_needs_digits_only" in out


def test_render_filled_hides_skip_sentinels_from_the_dossier(tmp_db, tmp_path):
    init_db()
    """__SKIP__ and friends are bookkeeping, not answers — printing them as if
    they were content makes the dossier harder to read, not more honest."""
    job = _job(url="https://acme.recruitee.com/o/eng3")
    out = apply_service._render_filled(
        job, {"Beginner": "skipped"}, {"screenshots_dir": str(tmp_path)}, {"Beginner": "__SKIP__"}
    )
    assert "__SKIP__" not in out


def test_render_filled_without_answers_still_renders(tmp_db, tmp_path):
    """The dossier section is additive: callers that pass no answers get the
    original message rather than an empty 'What will be sent' block."""
    init_db()
    job = _job(url="https://acme.recruitee.com/o/eng4")
    out = apply_service._render_filled(job, {"Name": "filled"}, {"screenshots_dir": str(tmp_path)})
    assert "What will be sent" not in out
    assert "To submit" in out


def test_record_submitted_tells_the_operator_to_check_spam(tmp_db, tmp_path):
    """ATS confirmations to a plus-alias are flagged as spam routinely — the
    holepunch one was. Gmail keeps learning from what gets rescued, so the useful
    moment to look is right after applying, while it is obvious what to look for."""
    init_db()
    job = _job(url="https://acme.recruitee.com/o/eng5")
    app = Application.create(job=job, status="filled", form_data="{}", email_ref="zz")

    out = apply_service._record_submitted(
        app, job, {}, "zz9900", {"screenshots_dir": str(tmp_path)}
    )

    assert "spam" in out.lower()
    assert "zz9900" in out, "o alias tem que aparecer, senão não dá pra procurar"


# ── override merging ────────────────────────────────────────────────────────


def test_merge_overrides_replaces_by_exact_key():
    merged, unmatched = apply_service._merge_overrides({"Phone": "old"}, {"Phone": "new"})
    assert merged == {"Phone": "new"}
    assert unmatched == []


def test_merge_overrides_matches_across_required_marker_and_newline():
    """The seeq #3322 case: the stored label carries Workable's own-line marker.

    Without normalisation this produced TWO entries for one textarea, and the
    last one written silently won.
    """
    stored = {"*\n3 References (1 Direct Manager)": "old text"}
    merged, unmatched = apply_service._merge_overrides(
        stored, {"3 References (1 Direct Manager)": "new text"}
    )
    assert merged == {"*\n3 References (1 Direct Manager)": "new text"}
    assert unmatched == []


def test_merge_overrides_ignores_case_and_extra_whitespace():
    stored = {"First  name": "Alberto"}
    merged, _ = apply_service._merge_overrides(stored, {"first name": "Beto"})
    assert merged == {"First  name": "Beto"}


def test_merge_overrides_keeps_unmatched_key_and_reports_it():
    """An unmatched key still applies — that is how `Choose file` gets skipped."""
    merged, unmatched = apply_service._merge_overrides({"Phone": "x"}, {"Choose file": "__SKIP__"})
    assert merged == {"Phone": "x", "Choose file": "__SKIP__"}
    assert unmatched == ["Choose file"]


def test_merge_overrides_refuses_to_guess_between_ambiguous_stored_keys():
    stored = {"*\nName": "a", "Name": "b"}
    merged, unmatched = apply_service._merge_overrides(stored, {" name ": "c"})
    assert merged["*\nName"] == "a"
    assert merged["Name"] == "b"
    assert unmatched == [" name "]


def test_merge_overrides_without_overrides_copies_stored():
    stored = {"Phone": "x"}
    merged, unmatched = apply_service._merge_overrides(stored, None)
    assert merged == stored
    assert merged is not stored
    assert unmatched == []


def test_unmatched_warning_is_empty_when_everything_matched():
    assert apply_service._unmatched_warning([]) == ""


def test_unmatched_warning_names_every_offending_key():
    warning = apply_service._unmatched_warning(["Choose file", "Typo"])
    assert "2 override key(s)" in warning
    assert "'Choose file'" in warning
    assert "'Typo'" in warning
