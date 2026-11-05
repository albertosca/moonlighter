"""Only a submitted application feeds the answer bank."""

import json

from moonlighter.core.db import AnswerBankEntry, init_db
from moonlighter.mcp_tools.applications import update_status
from tests.mcp_tools._records import create_application, create_job


async def test_update_status_submitted_promotes_bank_eligible_answers(temporary_database):
    init_db()

    job = create_job(temporary_database, url="https://x.com/promote1")
    create_application(
        job,
        form_data=json.dumps(
            {
                "Do you have 5+ years of Python experience?": {
                    "answer": "Yes",
                    "kind": "boolean",
                },
                "Why do you want to work here?": {"answer": "custom essay", "kind": "long_text"},
            }
        ),
    )

    await update_status(job_id=job.id, status="submitted")

    entry = AnswerBankEntry.get(
        AnswerBankEntry.normalized_question == "do you have 5+ years of python experience"
    )
    assert entry.answer == "Yes"
    assert AnswerBankEntry.select().where(AnswerBankEntry.kind == "long_text").count() == 0


async def test_update_status_non_submitted_does_not_promote(temporary_database):
    init_db()

    job = create_job(temporary_database, url="https://x.com/promote2")
    # Deliberately a bank-eligible, non-sensitive label: with a demographic one
    # ("Gender") the assertion below would pass for the wrong reason —
    # is_sensitive_label blocks promotion regardless of status — and would stop
    # proving anything about the status gate.
    create_application(
        job,
        form_data=json.dumps({"Do you know Kubernetes?": {"answer": "Yes", "kind": "boolean"}}),
    )

    await update_status(job_id=job.id, status="screening")

    assert AnswerBankEntry.select().count() == 0


async def test_update_status_submitted_with_legacy_flat_form_data_does_not_crash(
    temporary_database,
):
    # create_application()'s own default fixture ('{"Q": "A"}') predates this
    # feature's {"answer":..., "kind":...} shape, and many unrelated tests in this
    # file call update_status(status="submitted") against that default (e.g.
    # test_update_status_syncs_job_status above). This test pins the "does not
    # crash" behavior explicitly rather than relying on that incidental coverage.
    init_db()

    job = create_job(temporary_database, url="https://x.com/promote3")
    create_application(job)  # default form_data='{"Q": "A"}'

    result = await update_status(job_id=job.id, status="submitted")

    assert "submitted" in result
    assert AnswerBankEntry.select().count() == 0
