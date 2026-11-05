"""verify_job words its answers and stores its fields exactly."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.jobs import verify_job

from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result


async def test_verify_job_result_text_and_stored_fields_are_pinned(temporary_database):
    init_db()
    job = Job.create(
        source="manual",
        company="Acme",
        title="Eng",
        url="https://x.com/pin/v1",
        status="needs_review",
        score=None,
    )
    with patch(
        "moonlighter.discovery.manual.jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(9.0, caveats=["visa"])),
    ):
        result = await verify_job(
            job.id,
            "a pasted page that is long enough to score",
            CONFIG,
            profile=PROFILE,
            caller=MagicMock(),
        )
    assert result == (
        "✓ NEW — Acme / Eng\n"
        "Score: 9.0/10  (threshold: 7.0)\n"
        "Notes: match\n"
        "Caveats:\n"
        "  ⚠ visa\n"
        f"id={job.id}"
    )
    stored = Job.get_by_id(job.id)
    assert stored.description == "a pasted page that is long enough to score"
    assert stored.score == 9.0
    assert stored.score_notes == "match"
    assert stored.caveats == '["visa"]'
    assert (stored.salary_min, stored.salary_max) == (150000, 200000)
    assert (stored.salary_currency, stored.salary_source) == ("USD", "llm_estimate")
    assert stored.status == "new"


async def test_verify_job_rejection_messages_are_pinned_exactly(temporary_database):
    init_db()
    assert await verify_job(999, "x", CONFIG, profile=PROFILE, caller=MagicMock()) == (
        "Job #999 not found."
    )
    settled = Job.create(
        source="manual", company="Acme", title="Eng", url="https://x.com/pin/v2", status="new"
    )
    assert await verify_job(settled.id, "x", CONFIG, profile=PROFILE, caller=MagicMock()) == (
        f"Job #{settled.id} is not pending verification (status: 'new')."
    )
    pending = Job.create(
        source="manual",
        company="Acme",
        title="Eng",
        url="https://x.com/pin/v3",
        status="needs_review",
    )
    assert await verify_job(
        pending.id, "  tiny  ", CONFIG, profile=PROFILE, caller=MagicMock()
    ) == (
        f"That paste is too short to score (4 chars — need at least 30). Job #{pending.id} "
        "stays pending — open https://x.com/pin/v3 and copy the whole page."
    )
