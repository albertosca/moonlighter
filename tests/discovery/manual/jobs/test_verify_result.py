"""verify_job tells its caller what happened by kind, the way register and prepare do."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.manual.verification import VerifyKind, verify_job
from tests.discovery.fake_scan import CONFIG, PROFILE, evaluation_result

LONG_PAGE = "a pasted page that is long enough to score"


def _job(url, status="needs_review"):
    return Job.create(source="manual", company="Acme", title="Eng", url=url, status=status)


async def _verify(job_id, page_text=LONG_PAGE):
    evaluate = AsyncMock(return_value=evaluation_result(8.0))
    with patch("moonlighter.discovery.manual.verification.evaluate_job", new=evaluate):
        return await verify_job(job_id, page_text, CONFIG, profile=PROFILE, caller=MagicMock())


async def test_each_outcome_has_its_kind_and_the_job_id(temporary_database):
    init_db()
    settled = _job("https://x.com/kind/1", status="new")
    pending = _job("https://x.com/kind/2")
    scored = _job("https://x.com/kind/3")

    outcomes = {
        "missing": await _verify(999),
        "settled": await _verify(settled.id),
        "short": await _verify(pending.id, "  "),
        "scored": await _verify(scored.id),
    }

    assert {name: result.kind for name, result in outcomes.items()} == {
        "missing": VerifyKind.JOB_NOT_FOUND,
        "settled": VerifyKind.NOT_PENDING,
        "short": VerifyKind.PASTE_TOO_SHORT,
        "scored": VerifyKind.SCORED,
    }
    assert [result.job_id for result in outcomes.values()] == [
        999,
        settled.id,
        pending.id,
        scored.id,
    ]
    assert outcomes["missing"].message == "Job #999 not found."


async def test_a_paste_that_copies_a_stored_job_is_a_duplicate(temporary_database):
    init_db()
    page = "A long and complete job description, word for word the same in both rows."
    Job.create(
        source="manual", company="Acme", title="Eng", url="https://x.com/kind/4", description=page
    )
    pending = _job("https://x.com/kind/5")

    result = await _verify(pending.id, page)

    assert result.kind is VerifyKind.DUPLICATE
    assert "archived as a duplicate" in result.message
