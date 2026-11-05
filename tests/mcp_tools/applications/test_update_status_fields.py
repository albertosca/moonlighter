"""update_status appends notes, keeps what it was not given and stamps updated_at."""

from moonlighter.core.db import Application, init_db
from moonlighter.mcp_tools.applications import update_status
from tests.mcp_tools._records import create_application, create_job


async def test_update_status_with_notes(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/us2")
    create_application(job)

    await update_status(
        job_id=job.id,
        status="interviews",
        notes="Scheduled for Monday",
    )
    app = Application.get(Application.job == job)
    assert "Scheduled for Monday" in app.notes


async def test_update_status_with_next_action(temporary_database):
    init_db()
    job = create_job(temporary_database, url="https://x.com/us3")
    create_application(job)

    result = await update_status(job_id=job.id, status="screening", next_action="Call Friday")
    app = Application.get(Application.job == job)
    assert app.next_action == "Call Friday"
    assert "Call Friday" in result


async def test_update_status_appends_multiple_notes_instead_of_overwriting(temporary_database):
    """Calling update_status twice with notes appends, it does not clobber history."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us7")
    create_application(job)

    await update_status(job_id=job.id, status="screening", notes="First note")
    await update_status(job_id=job.id, status="interviews", notes="Second note")
    app = Application.get(Application.job == job)
    assert "First note" in app.notes
    assert "Second note" in app.notes
    # Second note comes after the first in the accumulated history.
    assert app.notes.index("First note") < app.notes.index("Second note")


async def test_update_status_without_notes_preserves_existing_notes(temporary_database):
    """Omitting `notes` on a later call must not erase previously stored notes."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us8")
    create_application(job)

    await update_status(job_id=job.id, status="screening", notes="Keep me")
    await update_status(job_id=job.id, status="interviews")
    app = Application.get(Application.job == job)
    assert "Keep me" in app.notes


async def test_update_status_without_next_action_preserves_existing_value(temporary_database):
    """Omitting `next_action` must not clear a previously set one."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us9")
    create_application(job, next_action="original follow-up")

    result = await update_status(job_id=job.id, status="screening")
    app = Application.get(Application.job == job)
    assert app.next_action == "original follow-up"
    assert "Next action" not in result


async def test_update_status_updates_updated_at_timestamp(temporary_database):
    """updated_at must move forward on a successful status change."""
    init_db()
    job = create_job(temporary_database, url="https://x.com/us11")
    app = create_application(job)
    original_updated_at = app.updated_at

    await update_status(job_id=job.id, status="screening")
    refreshed = Application.get(Application.job == job)
    assert refreshed.updated_at >= original_updated_at
