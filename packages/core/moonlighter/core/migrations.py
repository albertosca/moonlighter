"""The numbered schema migration steps for the local SQLite store; migration_runner applies them."""

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol


class MigrationDatabase(Protocol):
    """The slice of a peewee database the migrations use.

    peewee's stubs leave `execute_sql` and `connection` untyped, so annotating with
    `peewee.Database` would make every call an untyped-call error under strict mypy.
    """

    def execute_sql(self, sql: str, params: tuple[Any, ...] | None = None) -> sqlite3.Cursor: ...

    def atomic(self) -> AbstractContextManager[Any]: ...

    def connection(self) -> sqlite3.Connection: ...


def _has_column(db: MigrationDatabase, table: str, column: str) -> bool:
    cursor = db.execute_sql(f"PRAGMA table_info({table})")
    return column in {row[1] for row in cursor.fetchall()}


def _m001_application_email_ref(db: MigrationDatabase) -> None:
    if not _has_column(db, "application", "email_ref"):
        db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")
    db.execute_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS application_email_ref "
        "ON application (email_ref) WHERE email_ref IS NOT NULL"
    )


def _m002_application_current_stage(db: MigrationDatabase) -> None:
    if not _has_column(db, "application", "current_stage"):
        db.execute_sql("ALTER TABLE application ADD COLUMN current_stage VARCHAR(255) NULL")


def _m003_job_closed_at(db: MigrationDatabase) -> None:
    if not _has_column(db, "job", "closed_at"):
        db.execute_sql("ALTER TABLE job ADD COLUMN closed_at DATETIME NULL")


def _m004_unify_closed_into_archived(db: MigrationDatabase) -> None:
    # 'closed' (gone from source) and 'archived' (triaged out) are one status
    # from the operator's point of view (Alberto, 2026-08-24) — closed_at alone
    # keeps recording why a job left the queue.
    if _has_column(db, "job", "status"):
        db.execute_sql("UPDATE job SET status = 'archived' WHERE status = 'closed'")


def _m005_backfill_job_status_from_applications(db: MigrationDatabase) -> None:
    # One-shot repair for the drift found 2026-08-21 (jobs still 'new' with a
    # live Application). Forward writers now sync via job_status.sync_job_status.
    needed = (
        _has_column(db, "job", "status")
        and _has_column(db, "application", "status")
        and _has_column(db, "application", "job_id")
    )
    if not needed:
        return
    db.execute_sql(
        "UPDATE job SET status = 'applied' WHERE id IN ("
        "SELECT job_id FROM application WHERE status IN "
        "('submitted', 'screening', 'interviews', 'offer'))"
    )
    db.execute_sql(
        "UPDATE job SET status = 'rejected' WHERE id IN ("
        "SELECT job_id FROM application WHERE status = 'rejected')"
    )


def _m006_fix_invented_onsite_remote_types(db: MigrationDatabase) -> None:
    # The old normalize_remote_type invented 'onsite' for any unrecognized
    # location (English-only vocabulary + onsite default) — live bug iFood
    # #2811 ("Remoto" → onsite). Since the regional filter cuts onsite/hybrid
    # outside Belo Horizonte deterministically, an invented onsite is an
    # invented archive. Only 'onsite' rows are touched: the API remote flags
    # never produced that value. SQL mirrors the fixed normalizer's order.
    if not (_has_column(db, "job", "remote_type") and _has_column(db, "job", "location")):
        return
    db.execute_sql(
        "UPDATE job SET remote_type = 'hybrid' WHERE remote_type = 'onsite' AND ("
        "lower(location) LIKE '%hybrid%' OR location LIKE '%íbrido%' "
        "OR lower(location) LIKE '%hibrido%')"
    )
    db.execute_sql(
        "UPDATE job SET remote_type = 'remote' WHERE remote_type = 'onsite' AND ("
        "lower(location) LIKE '%remote%' OR lower(location) LIKE '%remoto%')"
    )
    db.execute_sql(
        "UPDATE job SET remote_type = NULL WHERE remote_type = 'onsite' AND NOT ("
        "lower(location) LIKE '%on-site%' OR lower(location) LIKE '%onsite%' "
        "OR lower(location) LIKE '%presencial%' OR lower(location) LIKE '%in office%' "
        "OR lower(location) LIKE '%in-office%')"
    )


MIGRATIONS: list[tuple[int, str, Callable[[MigrationDatabase], None]]] = [
    (1, "application_email_ref", _m001_application_email_ref),
    (2, "application_current_stage", _m002_application_current_stage),
    (3, "job_closed_at", _m003_job_closed_at),
    (4, "unify_closed_into_archived", _m004_unify_closed_into_archived),
    (5, "backfill_job_status_from_applications", _m005_backfill_job_status_from_applications),
    (6, "fix_invented_onsite_remote_types", _m006_fix_invented_onsite_remote_types),
]
