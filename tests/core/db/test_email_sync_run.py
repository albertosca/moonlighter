"""EmailSyncRun: one row per complete mailbox sweep."""

from moonlighter.core.db import EmailSyncRun, init_db


def test_a_sync_run_records_when_it_finished(temporary_database):
    init_db()
    run = EmailSyncRun.create()
    assert EmailSyncRun.get_by_id(run.id).finished_at is not None
