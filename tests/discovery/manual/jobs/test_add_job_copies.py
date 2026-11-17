"""add_job archives a copy of a stored job instead of scoring it again."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.jobs import add_job
from tests.discovery.fake_scan import CONFIG, PROFILE, evaluation_result

TEXT = "We build Rails apps for payments. Remote in Brazil."


async def test_a_copy_is_saved_as_an_archived_duplicate_without_scoring(temporary_database):
    init_db()
    original = Job.create(
        source="recruitee", company="Tether", title="Eng", url="https://x/1", description=TEXT
    )
    evaluator = AsyncMock(return_value=evaluation_result(9.0))
    with patch("moonlighter.discovery.manual.jobs.evaluate_job", new=evaluator):
        message = await add_job(
            "https://x/1-9", "Tether", "Eng", TEXT, CONFIG, PROFILE, MagicMock()
        )
    assert message == (
        f"Copy of job #{original.id} (Tether/Eng): saved as an archived duplicate, not scored."
    )
    evaluator.assert_not_awaited()
    copy = Job.get(Job.url == "https://x/1-9")
    assert (copy.status, copy.duplicate_of_id) == ("archived", original.id)


async def test_a_tracked_copy_points_at_the_original(temporary_database):
    init_db()
    original = Job.create(
        source="recruitee", company="Tether", title="Eng", url="https://x/1", description=TEXT
    )
    message = await add_job(
        "https://x/1-9", "Tether", "Eng", TEXT, CONFIG, PROFILE, MagicMock(), track=True
    )
    assert message.endswith(
        f"Track the original instead: register_application(job_id={original.id})."
    )
    assert Job.get(Job.url == "https://x/1-9").status == "archived"
