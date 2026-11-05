"""InHire publishes which built-in fields are required, not its questions.

`GET https://api.inhire.app/job-posts/public/pages/{job_id}` with header
`X-Tenant: <tenant>` carries `settings.requiredFields` as ids (`linkedin`,
`salary`, `curriculum`, `location`). Custom questions are only reachable after
an application is submitted, so the sheet still comes from a paste; the ids
tell the person up front what the form will insist on. Verified 2026-09-25
(bancada ats-form-apis).
"""

import logging
import re

import httpx

from moonlighter.application.assisted.questions import FormQuestion
from moonlighter.application.assisted.sources.base import UUID_PATTERN, SourceMatch
from moonlighter.core.db import Job

API = "https://api.inhire.app/job-posts/public/pages/{job_id}"
HEADERS = {"User-Agent": "moonlighter/0.1"}

logger = logging.getLogger(__name__)

_URL = re.compile(rf"https?://(?P<tenant>[\w-]+)\.inhire\.app/vagas/(?P<job_id>{UUID_PATTERN})")

_LABELS = {
    "linkedin": "LinkedIn",
    "salary": "Salary expectation",
    "curriculum": "CV",
    "location": "Location",
}


def tenant_and_job_from_url(url: str) -> tuple[str, str] | None:
    match = _URL.search(url)
    return (match["tenant"], match["job_id"]) if match else None


def parse_required_fields(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    settings = payload.get("settings")
    required_ids = settings.get("requiredFields") if isinstance(settings, dict) else None
    if not isinstance(required_ids, list):
        return ()
    field_ids = [_field_id(entry) for entry in required_ids]
    return tuple(_LABELS.get(field_id, field_id) for field_id in field_ids if field_id)


def _field_id(entry: object) -> str:
    """A required entry is usually a bare id; an object carries it as `id` or `name`."""
    if isinstance(entry, dict):
        return str(entry.get("id") or entry.get("name") or "")
    return str(entry) if entry else ""


async def fetch_inhire_required_fields(
    tenant: str, job_id: str, client: httpx.AsyncClient
) -> tuple[str, ...]:
    response = await client.get(API.format(job_id=job_id), headers={**HEADERS, "X-Tenant": tenant})
    if response.status_code != httpx.codes.OK:
        logger.warning(
            "inhire job page for %s/%s unavailable: HTTP %s", tenant, job_id, response.status_code
        )
        return ()
    return parse_required_fields(response.json())


class InHireSource:
    name = "inhire"

    def match(self, job: Job) -> SourceMatch | None:
        found = tenant_and_job_from_url(job.url)
        return SourceMatch(self, found) if found else None

    async def questions(
        self,
        match: SourceMatch,  # noqa: ARG002 - QuestionSource's signature; InHire publishes no questions, so nothing is read
        client: httpx.AsyncClient,  # noqa: ARG002 - QuestionSource's signature; InHire publishes no questions, so nothing is read
    ) -> list[FormQuestion]:
        return []

    async def required_fields(
        self, match: SourceMatch, client: httpx.AsyncClient
    ) -> tuple[str, ...]:
        tenant, job_id = match.locator
        return await fetch_inhire_required_fields(tenant, job_id, client)
