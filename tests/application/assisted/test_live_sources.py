"""Live checks against the real ATSes — run with `uv run pytest -m e2e`.

Each test picks a posting that is open right now from the ATS's own listing,
so it does not rot as postings close. A skipped e2e counts as a failure here.
"""

import httpx
import pytest

from moonlighter.application.assisted.questions import QuestionKind
from moonlighter.application.assisted.sources.base import (
    SourceMatch,
    questions_or_empty,
    required_fields_or_empty,
)
from moonlighter.application.assisted.sources.inhire import InHireSource
from moonlighter.application.assisted.sources.lever import LeverSource
from moonlighter.application.assisted.sources.workable import WorkableSource

pytestmark = pytest.mark.e2e
HEADERS = {"User-Agent": "moonlighter/0.1"}

# Tried in order; the first with an open posting is used. A company with no
# openings today is not drift, so each check moves on before failing.
WORKABLE_ACCOUNTS = ("seeq", "devsu")
LEVER_COMPANIES = ("palantir",)
INHIRE_TENANTS = ("infleet", "alliage")


async def _first_workable_shortcode(client: httpx.AsyncClient) -> str:
    for account in WORKABLE_ACCOUNTS:
        response = await client.get(f"https://apply.workable.com/api/v1/widget/accounts/{account}")
        if response.status_code == 200 and (jobs := response.json().get("jobs")):
            return str(jobs[0]["shortcode"])
    pytest.fail(f"no open Workable posting at {WORKABLE_ACCOUNTS}; add an account with openings")


async def _first_lever_posting(client: httpx.AsyncClient) -> tuple[str, str]:
    for company in LEVER_COMPANIES:
        response = await client.get(f"https://api.lever.co/v0/postings/{company}?mode=json&limit=1")
        if response.status_code == 200 and (postings := response.json()):
            return company, str(postings[0]["id"])
    pytest.fail(f"no open Lever posting at {LEVER_COMPANIES}; add a company with openings")


async def _first_inhire_job(client: httpx.AsyncClient) -> tuple[str, str]:
    for tenant in INHIRE_TENANTS:
        response = await client.get(
            "https://api.inhire.app/job-posts/public/pages", headers={"X-Tenant": tenant}
        )
        if response.status_code == 200 and (jobs := response.json().get("jobsPage")):
            return tenant, str(jobs[0]["jobId"])
    pytest.fail(f"no open InHire posting at {INHIRE_TENANTS}; add a tenant with openings")


async def test_workable_live_form_has_a_required_question():
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        shortcode = await _first_workable_shortcode(client)
        questions = await questions_or_empty(SourceMatch(WorkableSource(), (shortcode,)), client)
    assert any(question.required for question in questions), questions


async def test_lever_live_form_has_a_required_question():
    async with httpx.AsyncClient(timeout=60, headers=HEADERS) as client:
        company, posting_id = await _first_lever_posting(client)
        questions = await questions_or_empty(
            SourceMatch(LeverSource(), (company, posting_id)), client
        )
    assert any(question.required for question in questions), questions
    # The standard fields alone satisfy the assertion above; only a card yields a
    # choice or a long-text question, so this one proves the cards were read.
    # "Additional information" is long text from the standard markup, not a card.
    assert any(
        (question.is_choice or question.kind is QuestionKind.LONG_TEXT)
        and question.label != "Additional information"
        for question in questions
    ), f"no question came from a Lever card — the custom questions were not read: {questions}"


async def test_inhire_live_job_lists_required_fields():
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        tenant, job_id = await _first_inhire_job(client)
        required = await required_fields_or_empty(
            SourceMatch(InHireSource(), (tenant, job_id)), client
        )
    assert required, "InHire returned no required fields for an open posting"
