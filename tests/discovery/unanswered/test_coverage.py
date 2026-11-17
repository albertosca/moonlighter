"""The rule marks only behind an unbroken chain of sweeps, and never over a row that moved."""

from datetime import timedelta

from moonlighter.core.db import Application, EmailSyncRun
from moonlighter.discovery import unanswered
from moonlighter.discovery.unanswered import _mark, mark_unanswered_applications
from tests.discovery.unanswered.clock import CONFIG, NOW


def _sweeps(*windows):
    """Replace the fixture's sweep with these (finished days ago, window start days ago)."""
    EmailSyncRun.delete().execute()
    for finished, start in windows:
        EmailSyncRun.create(
            finished_at=NOW - timedelta(days=finished), window_start=NOW - timedelta(days=start)
        )


def test_a_signal_older_than_the_swept_window_is_left_unswept(make_application):
    _sweeps((1, 31))
    application = make_application(60)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "submitted"
    assert result.unswept == [
        {"job_id": application.job_id, "company": "Company1", "title": "Eng", "days": 60}
    ]
    assert result.marked == []


def test_overlapping_sweeps_chain_back_to_the_oldest_start(make_application):
    _sweeps((1, 31), (25, 55), (50, 80))
    application = make_application(70)
    mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "no_response"


def test_a_gap_between_sweeps_ends_the_coverage(make_application):
    _sweeps((1, 31), (40, 120))
    application = make_application(60)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "submitted"
    assert [entry["job_id"] for entry in result.unswept] == [application.job_id]


def test_a_signal_exactly_at_the_window_start_is_covered(make_application):
    _sweeps((1, 50))
    application = make_application(50)
    mark_unanswered_applications(CONFIG, NOW)
    assert Application.get_by_id(application.id).status == "no_response"


def test_a_row_that_moved_since_it_was_read_is_not_overwritten(make_application):
    application = make_application(90)
    stale = Application.get_by_id(application.id)
    Application.update(status="screening", updated_at=NOW).where(
        Application.id == application.id
    ).execute()
    assert _mark(stale, 90, NOW) is False
    stored = Application.get_by_id(application.id)
    assert (stored.status, stored.notes) == ("screening", None)


def test_a_row_a_sync_moves_mid_run_is_neither_marked_nor_reported(make_application, monkeypatch):
    application = make_application(90)
    real_mark = unanswered._mark

    def sync_moves_it_first(row, days, now):
        Application.update(status="screening", updated_at=NOW).where(
            Application.id == row.id
        ).execute()
        return real_mark(row, days, now)

    monkeypatch.setattr(unanswered, "_mark", sync_moves_it_first)
    result = mark_unanswered_applications(CONFIG, NOW)
    assert result.marked == []
    assert Application.get_by_id(application.id).status == "screening"
