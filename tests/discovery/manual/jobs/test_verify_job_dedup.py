"""verify_job on a paste that is the text of a job already stored: a copy, no LLM call."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.verification import verify_job
from tests.discovery.fake_scan import CONFIG, PROFILE, evaluation_result

PAGE = "We build Rails apps for fintechs. Remote in Brazil, async team, mentoring juniors. " * 3


def _pending():
    return Job.create(
        source="inhire",
        company="Acme",
        title="Eng",
        url="https://acme.inhire.app/vagas/2",
        status="needs_review",
    )


async def test_a_paste_matching_a_stored_job_is_archived_as_its_copy(temporary_database):
    init_db()
    original = Job.create(
        source="greenhouse", company="Acme", title="Eng", url="https://x/1", description=PAGE
    )
    pending = _pending()
    evaluate = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.verification.evaluate_job", new=evaluate):
        answer = (
            await verify_job(pending.id, PAGE, CONFIG, profile=PROFILE, caller=MagicMock())
        ).message
    evaluate.assert_not_called()
    stored = Job.get_by_id(pending.id)
    assert (stored.status, stored.duplicate_of_id, stored.description) == (
        "archived",
        original.id,
        PAGE,
    )
    assert answer == (
        f"Job #{pending.id} is a copy of job #{original.id} (Acme/Eng): "
        "archived as a duplicate, not scored."
    )


async def test_a_paste_with_no_stored_twin_is_scored(temporary_database):
    init_db()
    pending = _pending()
    evaluate = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.verification.evaluate_job", new=evaluate):
        await verify_job(pending.id, PAGE, CONFIG, profile=PROFILE, caller=MagicMock())
    evaluate.assert_called_once()
    assert Job.get_by_id(pending.id).duplicate_of_id is None


async def test_a_pending_job_that_already_holds_the_text_is_not_its_own_copy(temporary_database):
    init_db()
    pending = Job.create(
        source="inhire",
        company="Acme",
        title="Eng",
        url="https://acme.inhire.app/vagas/3",
        status="needs_review",
        description=PAGE,
    )
    evaluate = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.verification.evaluate_job", new=evaluate):
        await verify_job(pending.id, PAGE, CONFIG, profile=PROFILE, caller=MagicMock())
    evaluate.assert_called_once()
    assert Job.get_by_id(pending.id).duplicate_of_id is None
