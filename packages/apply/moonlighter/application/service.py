"""Application service: detects the ATS, generates a draft (apply_jobs), submits
(confirm_apply), and retries (retry_apply).

The MCP tools in server.py are thin wrappers that call these functions passing
config/profile/caller. The logic lives here, testable in isolation.
"""

import contextlib
import json
import re
import secrets
import shutil
import statistics
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from moonlighter.application.answers.cv import CVNotFoundError, resolve_cv_path
from moonlighter.application.answers.email_alias import build_email_alias, inject_email_alias
from moonlighter.application.appliers.ashby import AshbyApplier
from moonlighter.application.appliers.base import (
    BaseApplier,
    detect_captcha,
    generate_answers,
    is_skip,
)
from moonlighter.application.appliers.greenhouse import GreenhouseApplier
from moonlighter.application.appliers.lever import LeverApplier
from moonlighter.application.appliers.recruitee import RecruiteeApplier
from moonlighter.application.appliers.smartrecruiters import SmartRecruitersApplier
from moonlighter.application.appliers.workable import WorkableApplier
from moonlighter.core import browser
from moonlighter.core.config import NEEDS_REVIEW_SENTINEL
from moonlighter.core.db import Application, Job
from moonlighter.core.llm import LLMCaller
from moonlighter.core.log import get_logger
from moonlighter.core.plugins import discover_entry_points
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)

_URL_RE = re.compile(r"https?://", re.IGNORECASE)
# Bounded quantifiers (RFC-ish local/domain/TLD sizes) on purpose: the unbounded form
# `[^\s@]+@[^\s@]+\.[^\s@]+` backtracks quadratically on a long non-matching run, and this
# runs on attacker-shaped LLM output — the very thing this branch defends against.
_EMAIL_RE = re.compile(r"[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,24}")
_PHONE_RE = re.compile(r"(?:\+?\d[\s\-().]*){9,}")

# A closed posting reads the same across ATS platforms regardless of applier --
# checked once, generically, before spending an ATS-detection + form-extraction
# pass on a page that was never a real application form to begin with.
_CLOSED_JOB_MARKERS = (
    "no longer accepting applications",
    "this job is no longer available",
    "position has been filled",
    "posting is closed",
)


async def _is_job_closed(page: Page) -> bool:
    """Best-effort: any error (detached page, unexpected DOM) means "don't
    know" -- defaults to False, never raises. Same page.inner_text('body')
    call base.py's _confirm_submitted already uses for the same reason."""
    try:
        body = (await page.inner_text("body")).lower()
    except Exception:
        return False
    return any(marker in body for marker in _CLOSED_JOB_MARKERS)


def _anomaly_reasons(
    answer: str, other_answers: list[str], is_closed_set: bool = False
) -> list[str]:
    """Reasons a free-text answer looks like exfiltration. Empty list = clean.
    Flags are advisory (they highlight, never block). Closed-set answers (a
    select/radio/checkbox choice, not free text) skip only the length check —
    their length reflects the option's label, not attacker-controlled content,
    and mixing them into the peer pool for OTHER fields' median was itself a
    source of false positives (see docs/superpowers/specs/2026-07-20-e2-anomaly-closed-set-design.md)."""
    reasons: list[str] = []
    if _URL_RE.search(answer):
        reasons.append("contains a URL")
    if _EMAIL_RE.search(answer):
        reasons.append("contains an email address")
    if _PHONE_RE.search(answer):
        reasons.append("contains a phone number")
    if not is_closed_set and len(other_answers) >= 3:
        median = statistics.median(len(a) for a in other_answers)
        if median > 0 and len(answer) > 3 * median:
            reasons.append("disproportionately long")
    return reasons


_APPLIER_CLASSES: list[type[BaseApplier]] = [
    GreenhouseApplier,
    LeverApplier,
    AshbyApplier,
    RecruiteeApplier,
    SmartRecruitersApplier,
    WorkableApplier,
    *cast("list[type[BaseApplier]]", discover_entry_points("moonlighter.appliers")),
]


@asynccontextmanager
async def page_session(config: dict[str, Any]) -> AsyncIterator[Page]:
    """Opens a fresh browser page for the duration of the block, closing it on
    exit (success or error) — DRYs the acquire/close boilerplate shared by
    `_draft_one` and `_submit_on_page`."""
    page = await browser.new_page(config)
    try:
        yield page
    finally:
        await page.close()


async def _hide_window_safe(page: Page) -> None:
    """Best-effort: a CDP window-state failure must never break the apply flow."""
    try:
        await browser.hide_window(page)
    except Exception as e:
        logger.debug("hide_window failed (non-critical): %s", e)


async def _show_window_safe(page: Page) -> None:
    """Best-effort: a CDP window-state failure must never break the apply flow."""
    try:
        await browser.show_window(page)
    except Exception as e:
        logger.debug("show_window failed (non-critical): %s", e)


async def detect_applier(
    page: Page, config: dict[str, Any], profile: dict[str, Any], source: str | None = None
) -> BaseApplier | None:
    """Detects which applier handles the current page.

    Source-first: if the scanner already tagged the job's ATS (`source`), trust it
    over the URL — this is how Recruitee's custom career domains (e.g.
    jobs.channable.com) get routed correctly even though the URL itself carries no
    "recruitee" signal. Falls back to the existing URL-based `.detect()` loop when
    there's no source match (or no source at all), preserving current behavior for
    every other ATS.
    """
    if source is not None:
        for cls in _APPLIER_CLASSES:
            if source == cls.SOURCE:
                return cls(page, config, profile)
    for cls in _APPLIER_CLASSES:
        applier = cls(page, config, profile)
        if await applier.detect():
            return applier
    return None


def _screenshot_path(job_id: int, name: str, config: dict[str, Any]) -> str:
    """Path to the screenshot shown to the human, derived from screenshots_dir (not hardcoded)."""
    return f"{config['screenshots_dir']}/{job_id}/{name}.png"


def archive_screenshots(job_id: int, config: dict[str, Any]) -> None:
    """Moves screenshots from a completed application into the 'done/' subdir, freeing space."""
    try:
        src = Path(config["screenshots_dir"]) / str(job_id)
        if not src.exists():
            return
        dst = Path(config["screenshots_dir"]) / "done" / str(job_id)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        logger.info("archive_screenshots: #%d → done/", job_id)
    except Exception as e:
        logger.debug("archive_screenshots: failed (non-critical) — %s", e)


# ── apply_jobs: generates drafts ────────────────────────────────────────────


async def apply_jobs(
    ids: list[int], config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    drafts = [await _draft_one(job_id, config, profile, caller) for job_id in ids]
    return "\n\n---\n".join(drafts)


async def _draft_one(
    job_id: int, config: dict[str, Any], profile: dict[str, Any], caller: LLMCaller
) -> str:
    """Opens the job, extracts the form, generates the answers, and saves the draft.
    Returns the draft text (or a warning) — never raises."""
    try:
        job = Job.get_by_id(job_id)
    except Job.DoesNotExist:
        return f"⚠️  Job #{job_id} not found."

    try:
        async with page_session(config) as page:
            await page.goto(job.url, timeout=30000)
            # SPA-heavy ATS pages (Recruitee, Workable, ...) often keep a background
            # connection open (chat widget, analytics beacon), so networkidle never
            # fires even though goto() already confirmed the page loaded and is usable.
            with contextlib.suppress(PlaywrightTimeout):
                await page.wait_for_load_state("networkidle", timeout=15000)
            await browser.save_screenshot(page, job_id, "01-job-page", config)

            if await _is_job_closed(page):
                job.status = "closed"
                job.closed_at = datetime.now()
                job.save()
                return f"⚠️  Job #{job_id} ({job.company}/{job.title}): posting appears closed. URL: {job.url}"

            applier = await detect_applier(page, config, profile, source=job.source)
            if not applier:
                return f"⚠️  Job #{job_id}: ATS not recognized. URL: {job.url}"
            reason = await applier.not_applicable_reason()
            if reason:
                return f"⚠️  Job #{job_id} ({job.company}/{job.title}): {reason}: {job.url}"

            fields, closed_set_fields = await applier.extract_fields()
            await browser.save_screenshot(page, job_id, "02-form", config)
            draft = await generate_answers(
                company=job.company,
                title=job.title,
                description=job.description or "",
                fields=fields,
                profile=profile,
                model=config["llm_model"],
                job_id=job_id,
                _caller=caller,
                config=config,
                job_location=job.location,
                job_remote_type=job.remote_type,
                closed_set_fields=closed_set_fields,
            )
            _save_draft(job, draft.answers)
            Job.update(status="applying").where(Job.id == job_id).execute()
            return _render_draft(job_id, job, draft)
    except Exception as e:
        return f"⚠️  Job #{job_id}: error — {e}"


def _save_draft(job: Job, answers: dict[str, str]) -> None:
    app, created = Application.get_or_create(
        job=job, defaults={"status": "draft", "form_data": json.dumps(answers)}
    )
    if not created:
        app.form_data = json.dumps(answers)
        app.status = "draft"
        app.updated_at = datetime.now()
        app.save()


def _render_draft(job_id: int, job: Job, draft: Any) -> str:
    lines = [f"\n## Draft — Job #{job_id}: {job.company} / {job.title}"]
    if draft.error:
        lines.append(f"⚠️ Error generating answers: {draft.error}")

    needs_review = [
        field for field, answer in draft.answers.items() if answer == NEEDS_REVIEW_SENTINEL
    ]
    if needs_review:
        lines.append(
            "\n🚫 NEED YOUR DECISION (not filled — work authorization/visa, "
            "job's country undefined):"
        )
        lines += [f"  - {field}" for field in needs_review]
        lines.append(
            f"Answer in confirm_apply: "
            f'`confirm_apply(job_id={job_id}, answers={{"<field>": "Yes/No"}})`'
        )

    scannable = {
        f: a
        for f, a in draft.answers.items()
        if a != NEEDS_REVIEW_SENTINEL and f not in draft.pre_populated_fields
    }
    flagged: list[str] = []
    for field, answer in scannable.items():
        peers = [a for g, a in scannable.items() if g != field and g not in draft.closed_set_fields]
        reasons = _anomaly_reasons(answer, peers, is_closed_set=field in draft.closed_set_fields)
        if reasons:
            flagged.append(f"  - **{field}**: {', '.join(reasons)}")
    if flagged:
        lines.append(
            "\n⚠️ REVIEW CAREFULLY — answers with signs of exfiltration "
            "(could be content injected by the job):"
        )
        lines += flagged

    for field, answer in draft.answers.items():
        if answer != NEEDS_REVIEW_SENTINEL:
            lines.append(f"\n**{field}**\n{answer}")
    lines.append(f"\nTo approve and apply: `confirm_apply(job_id={job_id})`")
    lines.append('To edit: pass `answers={"field": "new answer"}` to confirm_apply')
    return "\n".join(lines)


def _normalize_label(label: str) -> str:
    """A label reduced to what identifies it, ignoring the form's decoration.

    Mirrors the normalisation the appliers use to find a field from a label
    (`* ` markers, non-breaking spaces, collapsed whitespace, case). Kept in
    step with `_find_field` in the Workable applier — if the two ever disagree,
    an override can be judged "unmatched" here and still hit a field there.
    """
    return re.sub(r"\s+", " ", re.sub(r"[* ]+", " ", label)).strip().lower()


def _merge_overrides(
    stored: dict[str, str], overrides: dict[str, str] | None
) -> tuple[dict[str, str], list[str]]:
    """Stored answers with the overrides applied, plus the keys that matched nothing.

    A plain `{**stored, **overrides}` requires the caller to reproduce the field
    label BYTE for byte, including the required marker Workable puts on a line
    of its own ("*\\n3 References…"). Get it slightly wrong and the override does
    not replace anything: it lands as a SECOND entry, both are sent to the
    applier, both resolve to the same element by the normalised label, and the
    one written last silently wins. Observed live on seeq #3322 (2026-08-05),
    where it was harmless only because both copies held the same text.

    So an override is matched against the stored keys by normalised label, and
    replaces the stored key in place. A key matching nothing is still applied —
    that is how a field the extractor missed gets answered, e.g. `Choose file` —
    but it is reported so a typo cannot pass for an edit. An AMBIGUOUS key
    (normalising to two or more stored keys) is left alone rather than guessed
    at, and reported the same way.
    """
    if not overrides:
        return dict(stored), []

    by_normal: dict[str, list[str]] = {}
    for key in stored:
        by_normal.setdefault(_normalize_label(key), []).append(key)

    merged = dict(stored)
    unmatched: list[str] = []
    for key, value in overrides.items():
        if key in merged:
            merged[key] = value
            continue
        candidates = by_normal.get(_normalize_label(key), [])
        if len(candidates) == 1:
            merged[candidates[0]] = value
        else:
            merged[key] = value
            unmatched.append(key)
    return merged, unmatched


def _unmatched_warning(unmatched: list[str]) -> str:
    if not unmatched:
        return ""
    listed = "\n".join(f"  - {key!r}" for key in unmatched)
    return (
        f"\n⚠️  {len(unmatched)} override key(s) matched no stored field and were added "
        f"as new answers:\n{listed}\n"
        "   If one of those was meant to EDIT an existing answer, it did not — check the "
        "label below and re-send it.\n"
    )


# ── confirm_apply: submits ──────────────────────────────────────────────────


async def confirm_apply(
    job_id: int, answers: dict[str, str] | None, config: dict[str, Any], profile: dict[str, Any]
) -> str:
    loaded = _load_draft(job_id)
    if loaded is None:
        return f"⚠️  Job #{job_id} not found or has no draft. Run apply_jobs first."
    job, app = loaded

    final_answers, unmatched = _merge_overrides(app.get_form_data(), answers)
    blocked = _pending_review_message(job_id, final_answers)
    if blocked:
        return blocked

    ref = secrets.token_urlsafe(4)[:6]
    _inject_reply_alias(final_answers, ref, config)

    try:
        cv_path = resolve_cv_path(job.company, config)
    except CVNotFoundError as e:
        return f"⚠️  {e}\n🚫 Not submitted — I won't upload the wrong CV."

    sent = await _submit_on_page(job, app, final_answers, ref, cv_path, config, profile)
    return _unmatched_warning(unmatched) + sent


def _load_draft(job_id: int) -> tuple[Job, Application] | None:
    try:
        job = Job.get_by_id(job_id)
        return job, Application.get(Application.job == job)
    except Job.DoesNotExist, Application.DoesNotExist:
        return None


def _pending_review_message(job_id: int, answers: dict[str, str]) -> str | None:
    """Blocks submission while there are work-authorization fields awaiting a decision."""
    pending = [k for k, v in answers.items() if v == NEEDS_REVIEW_SENTINEL]
    if not pending:
        return None
    bullets = "\n".join(f"  - {k}" for k in pending)
    return (
        f"🚫 Application #{job_id} NOT submitted — work authorization "
        f"fields awaiting your decision (job's country undefined):\n{bullets}"
        f"\nAnswer and re-run: "
        f'`confirm_apply(job_id={job_id}, answers={{"{pending[0]}": "Yes"}})`'
    )


def _reply_alias(ref: str, config: dict[str, Any]) -> str:
    """The alias this application will be answered at, for the operator to search."""
    base_address = config.get("email", {}).get("address")
    return build_email_alias(base_address, ref) if base_address else f"(alias +{ref})"


def _inject_reply_alias(answers: dict[str, str], ref: str, config: dict[str, Any]) -> None:
    """Injects candidaturas+<ref>@gmail.com into the email field BEFORE filling,
    so the company replies to the monitored account (autonomous sync by ref)."""
    base_address = config.get("email", {}).get("address")
    if base_address:
        inject_email_alias(answers, build_email_alias(base_address, ref))


async def _fill_open_page(
    page: Page,
    job: Job,
    answers: dict[str, str],
    cv_path: str,
    config: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[BaseApplier, dict[str, str]] | None:
    """Navigates, detects the ATS, fills, and takes the 03-filled screenshot on an
    ALREADY OPEN page. Returns (applier, fill_status) or None if the ATS is not
    recognized. Does NOT close the page — whoever opened it owns its lifecycle."""
    await page.goto(job.url, timeout=30000)
    with contextlib.suppress(PlaywrightTimeout):
        await page.wait_for_load_state("networkidle", timeout=15000)
    applier = await detect_applier(page, config, profile, source=job.source)
    if applier is None:
        return None
    await applier.prepare()
    fill_status = await _fill_form(applier, answers, cv_path, job.id)
    await browser.save_screenshot(page, job.id, "03-filled", config)
    return applier, fill_status


async def _submit_on_page(
    job: Job,
    app: Application,
    answers: dict[str, str],
    ref: str,
    cv_path: str,
    config: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    async with AsyncExitStack() as stack:
        page = await stack.enter_async_context(page_session(config))
        await _hide_window_safe(page)
        needs_review = False
        try:
            result = await _fill_open_page(page, job, answers, cv_path, config, profile)
            if result is None:
                return f"⚠️  ATS not recognized for job #{job.id}."
            applier, fill_status = result

            # A captcha means automation cannot finish this: the token minted in a
            # CDP-controlled tab is rejected server-side. Stop BEFORE clicking,
            # hand the window over, and genuinely let go of the browser.
            vendor = await detect_captcha(page)
            if vendor:
                await _show_window_safe(page)
                needs_review = True
                shot = _screenshot_path(job.id, "03-filled", config)
                stack.pop_all()  # the page outlives this block — do not close it
                await browser.detach()
                return _record_captcha(app, job, answers, ref, vendor, shot)

            outcome = await applier.submit()
            await browser.save_screenshot(page, job.id, "04-submitted", config)
            shot = _screenshot_path(job.id, "04-submitted", config)
            if isinstance(outcome, str) and outcome.startswith("failed"):
                await _show_window_safe(page)
                needs_review = True
                return _record_failed(app, job.id, outcome, fill_status, shot)
            if outcome == "unverified":
                await _show_window_safe(page)
                needs_review = True
                return _record_unverified(app, job, answers, ref, shot)
            return _record_submitted(app, job, answers, ref, config)
        except Exception as e:
            await _show_window_safe(page)
            needs_review = True
            app.status = "draft"
            app.save()
            Job.update(status="reviewed").where(Job.id == job.id).execute()
            return f"⚠️  Error submitting job #{job.id}: {e}"
        finally:
            # needs_review keeps the browser tab open for a human to fix — detach it
            # from the exit stack so leaving this block does not close it.
            if needs_review:
                stack.pop_all()
    raise AssertionError("unreachable")  # pragma: no cover


async def _fill_form(
    applier: BaseApplier, answers: dict[str, str], cv_path: str, job_id: int
) -> dict[str, str]:
    status = await applier.fill_form(answers, cv_path)
    failed = [field for field, s in status.items() if s.startswith("failed")]
    if failed:
        logger.warning("confirm_apply #%d: fields failed to fill: %s", job_id, failed)
    return status


def _record_failed(
    app: Application, job_id: int, outcome: str, fill_status: dict[str, str], shot: str
) -> str:
    """Submit failed (button not found, error, or validation) — reverts to draft."""
    app.status = "draft"
    app.save()
    Job.update(status="reviewed").where(Job.id == job_id).execute()
    problems = (
        ", ".join(f"{k}={s}" for k, s in fill_status.items() if s != "filled") or "all filled"
    )
    return (
        f"⚠️  Application #{job_id} was NOT submitted ({outcome}).\n"
        f"Problem fields: {problems}\n"
        f"Check {shot} and run retry_apply({job_id}) after fixing."
    )


def _record_captcha(
    app: Application, job: Job, answers: dict[str, str], ref: str, vendor: str, shot: str
) -> str:
    """Filled, stopped short of submitting, browser handed back to the human.

    Not a failure and not a submission: the form is complete and waiting. Marked
    needs_review so nothing auto-retries, and the answers are persisted so a
    later re-fill does not regenerate them.
    """
    now = datetime.now()
    app.status = "needs_review"
    app.applied_at = None
    app.form_data = json.dumps(answers)
    app.email_ref = ref
    app.updated_at = now
    note = (
        f"[{now.strftime('%Y-%m-%d')}] filled but NOT submitted — {vendor} captcha. "
        f"Browser detached and left open for manual submit."
    )
    app.notes = f"{app.notes}\n{note}" if app.notes else note
    app.save()
    Job.update(status="needs_review").where(Job.id == job.id).execute()
    return (
        f"🧩 Application #{job.id} ({job.company} / {job.title}) is FILLED but NOT submitted: "
        f"the form is protected by {vendor}.\n"
        f"A captcha solved in an automated tab is rejected by the server, so I stopped before "
        f"clicking and released the browser — it is no longer automation-controlled.\n"
        f"🖥️  The window is open with everything filled in. Solve the captcha and press submit.\n"
        f"Screenshot of what was filled: {shot}\n"
        f"→ Once sent: `update_status({job.id}, 'submitted')`"
    )


def _record_unverified(
    app: Application, job: Job, answers: dict[str, str], ref: str, shot: str
) -> str:
    """Clicked but could not confirm submission or detect an error. CONSERVATIVE: does
    not mark as sent (avoids a false positive) nor unlock a blind retry (avoids duplicating)."""
    now = datetime.now()
    app.status = "needs_review"
    app.applied_at = None
    app.form_data = json.dumps(answers)
    app.email_ref = ref
    app.updated_at = now
    note = (
        f"[{now.strftime('%Y-%m-%d')}] submit NOT confirmed — check {shot}. "
        f"If it was sent: update_status({job.id}, 'submitted'). "
        f"If NOT: update_status({job.id}, 'draft') and retry_apply({job.id})."
    )
    app.notes = f"{app.notes}\n{note}" if app.notes else note
    app.save()
    Job.update(status="needs_review").where(Job.id == job.id).execute()
    return (
        f"⚠️  Application #{job.id} ({job.company} / {job.title}): could NOT "
        f"confirm submission.\n"
        f"🚫 Did NOT mark as sent and will NOT re-submit on my own (avoids duplicating).\n"
        f"Check the screenshot: {shot}\n"
        f"→ If it was sent: `update_status({job.id}, 'submitted')`\n"
        f"→ If not: `update_status({job.id}, 'draft')` and `retry_apply({job.id})`"
    )


def _record_submitted(
    app: Application, job: Job, answers: dict[str, str], ref: str, config: dict[str, Any]
) -> str:
    now = datetime.now()
    app.status = "submitted"
    app.applied_at = now
    app.form_data = json.dumps(answers)
    app.updated_at = now
    app.email_ref = ref
    app.save()
    Job.update(status="applied").where(Job.id == job.id).execute()
    archive_screenshots(job.id, config)
    alias = _reply_alias(ref, config)
    return (
        f"✓ Application #{job.id} submitted and confirmed: {job.company} / {job.title}\n"
        f"📧 Tracking alias: {alias}\n"
        f"   Check spam now and rescue the confirmation if it landed there — ATS mail to a "
        f"plus-alias is flagged routinely, and Gmail learns from what you rescue."
    )


# ── fill_application: fills and STOPS (does not submit) ─────────────────────


async def fill_application(
    job_id: int, answers: dict[str, str] | None, config: dict[str, Any], profile: dict[str, Any]
) -> str:
    """Fills the form and STOPS before submit, for the human to review the
    03-filled screenshot. Persists status='filled' + answers (with alias) + ref."""
    loaded = _load_draft(job_id)
    if loaded is None:
        return f"⚠️  Job #{job_id} not found or has no draft. Run apply_jobs first."
    job, app = loaded

    final_answers, unmatched = _merge_overrides(app.get_form_data(), answers)
    blocked = _pending_review_message(job_id, final_answers)
    if blocked:
        return blocked

    ref = secrets.token_urlsafe(4)[:6]
    _inject_reply_alias(final_answers, ref, config)
    try:
        cv_path = resolve_cv_path(job.company, config)
    except CVNotFoundError as e:
        return f"⚠️  {e}\n🚫 Not filled — I won't upload the wrong CV."

    async with AsyncExitStack() as stack:
        page = await stack.enter_async_context(page_session(config))
        await _hide_window_safe(page)
        needs_review = False
        try:
            result = await _fill_open_page(page, job, final_answers, cv_path, config, profile)
            if result is None:
                return f"⚠️  ATS not recognized for job #{job.id}."
            _applier, fill_status = result
            app.status = "filled"
            app.form_data = json.dumps(final_answers)
            app.email_ref = ref
            app.updated_at = datetime.now()
            app.save()
            message = _unmatched_warning(unmatched) + _render_filled(
                job, fill_status, config, final_answers
            )
            if any(s.startswith("failed") for s in fill_status.values()):
                await _show_window_safe(page)
                needs_review = True
                message += "\n🖥️  Opened the browser — take a look and adjust manually if needed."
            return message
        except Exception as e:
            await _show_window_safe(page)
            needs_review = True
            return f"⚠️  Error filling job #{job.id}: {e}\n🖥️  Opened the browser — take a look."
        finally:
            # needs_review keeps the browser tab open for a human to fix — detach it
            # from the exit stack so leaving this block does not close it.
            if needs_review:
                stack.pop_all()
    raise AssertionError("unreachable")  # pragma: no cover


def _render_filled(
    job: Job,
    fill_status: dict[str, str],
    config: dict[str, Any],
    answers: dict[str, str] | None = None,
) -> str:
    """The review dossier: the screenshot plus every answer, in full.

    The screenshot only ever shows a scrolled slice of each textarea, so
    approving from it alone means approving text nobody read. The answers are
    already persisted — printing them is what turns the review into one.
    """
    shot = _screenshot_path(job.id, "03-filled", config)
    lines = [
        f"📝 Job #{job.id} ({job.company} / {job.title}) FILLED — not submitted.",
        f"Review the actual form in the screenshot: {shot}",
    ]
    failed = {field: s for field, s in fill_status.items() if s.startswith("failed")}
    if failed:
        lines.append("")
        lines.append("⚠️  Fields that failed to fill:")
        lines += [f"  - {field}: {reason}" for field, reason in failed.items()]

    if answers:
        lines.append("")
        lines.append("── What will be sent ──────────────────────────────────────────")
        for field, answer in answers.items():
            if is_skip(answer):  # bookkeeping sentinels are not content
                continue
            lines.append("")
            lines.append(f"### {field.replace(chr(0xA0), ' ').strip()}")
            lines.append(str(answer))
        lines.append("")
        lines.append("───────────────────────────────────────────────────────────────")

    lines.append(f"→ To submit: `submit_application({job.id})`")
    lines.append(
        f'→ To edit and re-fill: `fill_application({job.id}, answers={{"field": "value"}})`'
    )
    return "\n".join(lines)


# ── submit_application: submits an already-filled form ──────────────────────


async def submit_application(job_id: int, config: dict[str, Any], profile: dict[str, Any]) -> str:
    """Submits an already-filled application (status 'filled'). Re-fills from the
    saved answers (deterministic) and submits. Strict: never submits blindly."""
    loaded = _load_draft(job_id)
    if loaded is None:
        return f"⚠️  Job #{job_id} not found or has no draft. Run apply_jobs first."
    job, app = loaded
    if app.status != "filled":
        return (
            f"🚫 Job #{job_id} is not filled (status={app.status}). Run "
            f"`fill_application({job_id})` first — or `confirm_apply({job_id})` to "
            f"fill and submit in a single step."
        )
    try:
        cv_path = resolve_cv_path(job.company, config)
    except CVNotFoundError as e:
        return f"⚠️  {e}\n🚫 Not submitted — I won't upload the wrong CV."
    return await _submit_on_page(
        job, app, app.get_form_data(), app.email_ref or "", cv_path, config, profile
    )


async def retry_apply(job_id: int, config: dict[str, Any], profile: dict[str, Any]) -> str:
    try:
        app = Application.get(Application.job == Job.get_by_id(job_id))
    except Job.DoesNotExist, Application.DoesNotExist:
        return f"Job #{job_id} has no saved draft. Run apply_jobs(ids=[{job_id}]) first."
    if app.status == "needs_review":
        return (
            f"🚫 Job #{job_id} is in needs_review — may have already been sent. "
            f"Will NOT blindly re-submit (avoids a duplicate application).\n"
            f"→ If it was sent: `update_status({job_id}, 'submitted')`\n"
            f"→ If not: `update_status({job_id}, 'draft')` and then `retry_apply({job_id})`"
        )
    return await confirm_apply(job_id, None, config, profile)
