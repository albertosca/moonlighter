"""EmailSyncRun: one row per complete mailbox sweep."""

from datetime import datetime

from moonlighter.core.db import EmailSyncRun, init_db


def test_a_sync_run_records_when_it_finished(temporary_database):
    init_db()
    run = EmailSyncRun.create(window_start=datetime(2026, 10, 18))  # noqa: DTZ001 - naive local time
    stored = EmailSyncRun.get_by_id(run.id)
    assert stored.finished_at is not None
    assert stored.window_start == datetime(2026, 10, 18)  # noqa: DTZ001 - naive local time
