"""add_job answers without scoring when the input or the title says so."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual_jobs import add_job

from tests.discovery.scan_fakes import CONFIG, PROFILE, evaluation_result


async def test_add_job_missing_company_title(temporary_database):
    init_db()
    result = await add_job("https://x.com/1", "", "", "provided desc", CONFIG, PROFILE, MagicMock())
    assert "company" in result
    assert "title" in result


async def test_add_job_title_blocklist_archives(temporary_database):
    init_db()
    result = await add_job(
        "https://x.com/7", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "discarded by the title filter" in result
    job = Job.get(Job.url == "https://x.com/7")
    assert job.status == "archived"
    assert job.score == 0.0


async def test_add_job_title_blocklist_integrity_swallowed(temporary_database):
    init_db()
    # Pre-creates the URL to force IntegrityError in Job.create on the blocklist branch.
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/8", status="new")
    result = await add_job(
        "https://x.com/8", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert "discarded by the title filter" in result


async def test_add_job_early_return_messages_are_pinned_exactly(temporary_database):
    init_db()
    missing = await add_job("https://x.com/pin/4", "", "", "desc", CONFIG, PROFILE, MagicMock())
    assert missing == "Provide at least 'company' and 'title' along with the URL."
    filtered = await add_job(
        "https://x.com/pin/5", "Acme", "Staff Accountant", "desc", CONFIG, PROFILE, MagicMock()
    )
    assert filtered == "Job discarded by the title filter (pattern: 'staff accountant')."
    Job.create(source="manual", company="Acme", title="x", url="https://x.com/pin/6", status="new")
    with patch(
        "moonlighter.discovery.manual_jobs.evaluate_job",
        new=AsyncMock(return_value=evaluation_result(8.0)),
    ):
        conflict = await add_job(
            "https://x.com/pin/6", "Acme", "Eng", "desc", CONFIG, PROFILE, MagicMock()
        )
    assert conflict == "Job already in the database (URL conflict)."
