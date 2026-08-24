import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import peewee
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

_LOCK_RETRIES = 5
_LOCK_BACKOFF_S = 0.5
_BACKUP_KEEP = 5


def _has_column(db: Any, table: str, column: str) -> bool:
    cursor = db.execute_sql(f"PRAGMA table_info({table})")
    return column in {row[1] for row in cursor.fetchall()}


def _m001_application_email_ref(db: Any) -> None:
    if not _has_column(db, "application", "email_ref"):
        db.execute_sql("ALTER TABLE application ADD COLUMN email_ref VARCHAR(8) NULL")
    db.execute_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS application_email_ref "
        "ON application (email_ref) WHERE email_ref IS NOT NULL"
    )


def _m002_application_current_stage(db: Any) -> None:
    if not _has_column(db, "application", "current_stage"):
        db.execute_sql("ALTER TABLE application ADD COLUMN current_stage VARCHAR(255) NULL")


def _m003_job_closed_at(db: Any) -> None:
    if not _has_column(db, "job", "closed_at"):
        db.execute_sql("ALTER TABLE job ADD COLUMN closed_at DATETIME NULL")


def _m004_unify_closed_into_archived(db: Any) -> None:
    # 'closed' (gone from source) and 'archived' (triaged out) are one status
    # from the operator's point of view (Alberto, 2026-08-24) — closed_at alone
    # keeps recording why a job left the queue.
    if _has_column(db, "job", "status"):
        db.execute_sql("UPDATE job SET status = 'archived' WHERE status = 'closed'")


def _m005_backfill_job_status_from_applications(db: Any) -> None:
    # One-shot repair for the drift found 2026-08-21 (jobs still 'new' with a
    # live Application). Forward writers now sync via db.sync_job_status.
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


MIGRATIONS: list[tuple[int, str, Callable[[Any], None]]] = [
    (1, "application_email_ref", _m001_application_email_ref),
    (2, "application_current_stage", _m002_application_current_stage),
    (3, "job_closed_at", _m003_job_closed_at),
    (4, "unify_closed_into_archived", _m004_unify_closed_into_archived),
    (5, "backfill_job_status_from_applications", _m005_backfill_job_status_from_applications),
]


def current_version(db: Any) -> int:
    """Read-only: version of the schema currently applied to `db`. 0 when
    `schema_version` doesn't exist yet or holds no row (a pre-migration-system
    DB, e.g. one that already got the old ad-hoc ALTERs but never had this
    table). Never creates or writes anything — callers that need the table to
    exist go through `_ensure_schema_version_table` inside the migration's
    lock-retry region instead."""
    cursor = db.execute_sql("PRAGMA table_info(schema_version)")
    if not cursor.fetchall():
        return 0
    row = db.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _ensure_schema_version_table(db: Any) -> None:
    """Create `schema_version` and seed it at 0 if it doesn't exist yet. Only
    called from inside the lock-retry region in `run_migrations`, after the
    pre-migration backup, so it is retried on a B5 lock like every other
    migration write and never appears in the backup snapshot."""
    db.execute_sql("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = db.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        db.execute_sql("INSERT INTO schema_version (version) VALUES (0)")


def _backup(db: Any) -> Path:
    from moonlighter.core.config import moonlighter_home

    backups = Path(moonlighter_home()) / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = backups / f"pre-migration-{stamp}.db"
    target = sqlite3.connect(dest)
    try:
        db.connection().backup(target)  # consistent online backup, not a hot cp
    finally:
        target.close()
    for old in sorted(backups.glob("pre-migration-*.db"))[:-_BACKUP_KEEP]:
        old.unlink()
    return dest


def _run_locked(db: Any, name: str, action: Callable[[], None]) -> None:
    """Run `action` inside a transaction, retrying a bounded number of times
    when the failure is a "database is locked" error raised by peewee (the
    type every write through `db.atomic()`/`execute_sql` actually raises —
    NOT `sqlite3.OperationalError`, which is a distinct, unrelated type).
    Any other OperationalError, or the last attempt, re-raises immediately."""
    for attempt in range(_LOCK_RETRIES):  # pragma: no branch - always breaks or raises
        try:
            with db.atomic():
                action()
            return
        except peewee.OperationalError as e:
            if "locked" in str(e).lower() and attempt < _LOCK_RETRIES - 1:
                logger.warning("%s: DB locked, retrying (%d)", name, attempt + 1)
                time.sleep(_LOCK_BACKOFF_S)
                continue
            raise


def run_migrations(db: Any) -> list[str]:
    """Bring `db` up to the latest schema version, applying only pending
    migrations. Returns the names of the migrations actually applied (empty
    when the schema is already current). Takes a consistent pre-migration
    backup only when there is at least one pending migration. Each migration
    (and the schema_version table setup itself) runs in its own transaction,
    retried on a B5-style lock — a failure leaves the version at the last
    fully-applied migration, never a torn state."""
    version = current_version(db)
    pending = [(v, name, fn) for v, name, fn in MIGRATIONS if v > version]
    if not pending:
        return []
    _backup(db)
    _run_locked(db, "schema_version_table", lambda: _ensure_schema_version_table(db))
    applied: list[str] = []
    for v, name, fn in pending:

        def _apply(v: int = v, fn: Callable[[Any], None] = fn) -> None:
            fn(db)
            db.execute_sql("UPDATE schema_version SET version = ?", (v,))

        _run_locked(db, name, _apply)
        applied.append(name)
    return applied
