"""The 45-day rule: who is marked no_response, who is only listed, and when it does not run."""

from datetime import datetime, timedelta

import pytest

from moonlighter.core.db import Application, EmailSyncRun, Job, init_db
from moonlighter.discovery.unanswered import mark_unanswered_applications

NOW = datetime(2026, 11, 17, 10, 0)  # noqa: DTZ001 - the database stores naive local time
CONFIG = {"no_response_after_days": 45, "email_sync_max_age_days": 7}


@pytest.fixture
def make_application(temporary_database):
    init_db()
    EmailSyncRun.create(finished_at=NOW - timedelta(days=1))
    count = 0

    def _make(days_silent, status="submitted", notes=None, **fields):
        nonlocal count
        count += 1
        job = Job.create(
            source="manual",
            company=f"Company{count}",
            title="Eng",
            url=f"https://x/{count}",
            status="applied",
        )
        return Application.create(
            job=job,
            status=status,
            notes=notes,
            updated_at=NOW - timedelta(days=days_silent),
            **fields,
        )

    return _make


def test_44_days_stays_submitted_and_45_becomes_no_response(make_application):
    young = make_application(44)
    old = make_application(45)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(young.id).status == "submitted"
    stored = Application.get_by_id(old.id)
    assert stored.status == "no_response"
    assert stored.notes.endswith("no_response: no sign of life for 45 days")
    assert stored.updated_at == NOW
    assert Job.get_by_id(stored.job_id).status == "applied"
    assert [entry["job_id"] for entry in result.marked] == [old.job_id]
    assert result.marked[0] == {
        "job_id": old.job_id,
        "company": "Company2",
        "title": "Eng",
        "days": 45,
    }


def test_a_recent_dated_note_resets_the_clock(make_application):
    application = make_application(90, notes="[2026-11-01] acknowledgement: received")
    mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "submitted"


def test_an_old_dated_note_does_not_keep_it_alive(make_application):
    application = make_application(90, notes="[2026-08-01] acknowledgement: received")
    mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "no_response"


def test_a_malformed_or_future_note_falls_back_to_updated_at(make_application):
    malformed = make_application(60, notes="[2026-13-45] garbage\nno date here")
    future = make_application(60, notes="[2027-01-01] typo in the year")
    mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(malformed.id).status == "no_response"
    assert Application.get_by_id(future.id).status == "no_response"


def test_a_flagged_row_is_held_not_marked(make_application):
    application = make_application(90, reply_mailbox_unswept=True)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "submitted"
    assert [entry["job_id"] for entry in result.held] == [application.job_id]
    assert result.marked == []


@pytest.mark.parametrize("status", ["screening", "interviews", "offer"])
def test_later_stages_are_listed_never_changed(make_application, status):
    application = make_application(90, status=status)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == status
    assert [(entry["job_id"], entry["status"]) for entry in result.to_review] == [
        (application.job_id, status)
    ]


@pytest.mark.parametrize("status", ["draft", "filled", "rejected", "no_response"])
def test_other_statuses_are_out_of_scope(make_application, status):
    application = make_application(90, status=status)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == status
    assert (result.marked, result.to_review, result.held) == ([], [], [])


def test_no_recent_sync_marks_nothing(make_application):
    EmailSyncRun.delete().execute()
    EmailSyncRun.create(finished_at=NOW - timedelta(days=8))
    application = make_application(90)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "submitted"
    assert (result.ran, result.last_sync) == (False, (NOW - timedelta(days=8)).isoformat())


def test_a_sync_exactly_at_the_max_age_is_too_old(make_application):
    EmailSyncRun.delete().execute()
    EmailSyncRun.create(finished_at=NOW - timedelta(days=7))
    make_application(90)
    assert mark_unanswered_applications(CONFIG, NOW).ran is False


def test_a_sync_just_inside_the_max_age_runs(make_application):
    EmailSyncRun.delete().execute()
    EmailSyncRun.create(finished_at=NOW - timedelta(days=6, hours=23))
    make_application(90)
    assert mark_unanswered_applications(CONFIG, NOW).ran is True


def test_the_newest_sync_decides(make_application):
    EmailSyncRun.create(finished_at=NOW - timedelta(days=30))
    result = mark_unanswered_applications(CONFIG, NOW)
    assert (result.ran, result.last_sync) == (True, (NOW - timedelta(days=1)).isoformat())


def test_no_sync_ever_marks_nothing(make_application):
    EmailSyncRun.delete().execute()
    make_application(90)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert (result.ran, result.last_sync) == (False, None)


def test_a_second_run_does_not_mark_again(make_application):
    make_application(90)
    mark_unanswered_applications(CONFIG, NOW)
    assert mark_unanswered_applications(CONFIG, NOW).marked == []
