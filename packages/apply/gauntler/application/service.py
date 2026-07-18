"""Application service: detects the ATS, generates a draft (apply_jobs), submits
(confirm_apply), and retries (retry_apply).

The MCP tools in server.py are thin wrappers that call these functions passing
config/profile/caller. The logic lives here, testable in isolation.
"""

import json
import re
import secrets
import shutil
import statistics
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from gauntler.application.answers.cv import CVNotFoundError, resolve_cv_path
from gauntler.application.answers.email_alias import build_email_alias, inject_email_alias
from gauntler.application.appliers.ashby import AshbyApplier
from gauntler.application.appliers.base import BaseApplier, generate_answers
from gauntler.application.appliers.greenhouse import GreenhouseApplier
from gauntler.application.appliers.lever import LeverApplier
from gauntler.application.appliers.linkedin import LinkedInApplier
from gauntler.core import browser
from gauntler.core.config import NEEDS_REVIEW_SENTINEL
from gauntler.core.db import Application, Job
from gauntler.core.llm import LLMCaller
from gauntler.core.log import get_logger
from playwright.async_api import Page

logger = get_logger(__name__)

_URL_RE = re.compile(r"https?://", re.IGNORECASE)
# Bounded quantifiers (RFC-ish local/domain/TLD sizes) on purpose: the unbounded form
# `[^\s@]+@[^\s@]+\.[^\s@]+` backtracks quadratically on a long non-matching run, and this
# runs on attacker-shaped LLM output — the very thing this branch defends against.
_EMAIL_RE = re.compile(r"[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,24}")
_PHONE_RE = re.compile(r"(?:\+?\d[\s\-().]*){9,}")


def _anomaly_reasons(answer: str, other_answers: list[str]) -> list[str]:
    """Reasons a free-text answer looks like exfiltration. Empty list = clean.
    Flags are advisory (they highlight, never block)."""
    reasons: list[str] = []
    if _URL_RE.search(answer):
        reasons.append("contains a URL")
    if _EMAIL_RE.search(answer):
        reasons.append("contains an email address")
    if _PHONE_RE.search(answer):
        reasons.append("contains a phone number")
    if len(other_answers) >= 3:
        median = statistics.median(len(a) for a in other_answers)
        if median > 0 and len(answer) > 3 * median:
            reasons.append("disproportionately long")
    return reasons


_APPLIER_CLASSES = [LinkedInApplier, GreenhouseApplier, LeverApplier, AshbyApplier]


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
    page: Page, config: dict[str, Any], profile: dict[str, Any]
) -> BaseApplier | None:
    for cls in _APPLIER_CLASSES:
        applier = cls(page, config, profile)  # type: ignore[abstract]
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
            await page.wait_for_load_state("networkidle", timeout=15000)
            await browser.save_screenshot(page, job_id, "01-job-page", config)

            applier = await detect_applier(page, config, profile)
            if not applier:
                return f"⚠️  Job #{job_id}: ATS not recognized. URL: {job.url}"
            if isinstance(applier, LinkedInApplier) and not await applier.is_easy_apply():
                return (
                    f"⚠️  Job #{job_id} ({job.company}/{job.title}): does not have Easy Apply. "
                    f"Manual application required: {job.url}"
                )

            fields = await applier.extract_fields()
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
        peers = [a for g, a in scannable.items() if g != field]
        reasons = _anomaly_reasons(answer, peers)
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


# ── confirm_apply: submits ──────────────────────────────────────────────────


async def confirm_apply(
    job_id: int, answers: dict[str, str] | None, config: dict[str, Any], profile: dict[str, Any]
) -> str:
    loaded = _load_draft(job_id)
    if loaded is None:
        return f"⚠️  Job #{job_id} not found or has no draft. Run apply_jobs first."
    job, app = loaded

    final_answers = {**app.get_form_data(), **(answers or {})}
    blocked = _pending_review_message(job_id, final_answers)
    if blocked:
        return blocked

    ref = secrets.token_urlsafe(4)[:6]
    _inject_reply_alias(final_answers, ref, config)

    try:
        cv_path = resolve_cv_path(job.company, config)
    except CVNotFoundError as e:
        return f"⚠️  {e}\n🚫 Not submitted — I won't upload the wrong CV."

    return await _submit_on_page(job, app, final_answers, ref, cv_path, config, profile)


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
    await page.wait_for_load_state("networkidle", timeout=15000)
    applier = await detect_applier(page, config, profile)
    if applier is None:
        return None
    if isinstance(applier, LinkedInApplier):
        await applier.extract_fields()  # opens the modal
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
    return f"✓ Application #{job.id} submitted and confirmed: {job.company} / {job.title}"


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

    final_answers = {**app.get_form_data(), **(answers or {})}
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
            message = _render_filled(job, fill_status, config)
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


def _render_filled(job: Job, fill_status: dict[str, str], config: dict[str, Any]) -> str:
    shot = _screenshot_path(job.id, "03-filled", config)
    lines = [
        f"📝 Job #{job.id} ({job.company} / {job.title}) FILLED — not submitted.",
        f"Review the actual form in the screenshot: {shot}",
    ]
    failed = [field for field, s in fill_status.items() if s.startswith("failed")]
    if failed:
        lines.append(f"⚠️  Fields that failed to fill: {', '.join(failed)}")
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
