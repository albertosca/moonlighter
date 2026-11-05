"""Applies the numbered migrations to the local SQLite store, once each and in order, with a backup first."""

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import peewee

from moonlighter.core.config.paths import moonlighter_home
from moonlighter.core.log import get_logger
from moonlighter.core.migrations import MIGRATIONS, MigrationDatabase

logger = get_logger(__name__)

_LOCK_RETRIES = 5
_LOCK_BACKOFF_S = 0.5
_BACKUP_KEEP = 5


def current_version(db: MigrationDatabase) -> int:
    """Read-only: version of the schema currently applied to `db`.

    0 when `schema_version` doesn't exist yet or holds no row (a pre-migration-system DB, e.g. one
    that already got the old ad-hoc ALTERs but never had this table). Never creates or writes
    anything — callers that need the table to exist go through `_ensure_schema_version_table` inside
    the migration's lock-retry region instead.
    """
    cursor = db.execute_sql("PRAGMA table_info(schema_version)")
    if not cursor.fetchall():
        return 0
    row = db.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _ensure_schema_version_table(db: MigrationDatabase) -> None:
    """Create `schema_version` and seed it at 0 if it doesn't exist yet.

    Only called from inside the lock-retry region in `run_migrations`, after the pre-migration
    backup, so it is retried on a B5 lock like every other migration write and never appears in the
    backup snapshot.
    """
    db.execute_sql("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = db.execute_sql("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is None:
        db.execute_sql("INSERT INTO schema_version (version) VALUES (0)")


def _backup(db: MigrationDatabase) -> Path:
    backups = Path(moonlighter_home()) / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")  # noqa: DTZ005 - backup names carry naive local time, and the rotation below sorts them by name
    destination = backups / f"pre-migration-{stamp}.db"
    target = sqlite3.connect(destination)
    try:
        db.connection().backup(target)  # consistent online backup, not a hot cp
    finally:
        target.close()
    for old in sorted(backups.glob("pre-migration-*.db"))[:-_BACKUP_KEEP]:
        old.unlink()
    return destination


def _run_locked(db: MigrationDatabase, name: str, action: Callable[[], None]) -> None:
    """Run `action` inside a transaction, retrying a bounded number of times on a lock error.

    It retries only when the failure is a "database is locked" error raised by peewee (the type
    every write through `db.atomic()`/`execute_sql` actually raises — NOT
    `sqlite3.OperationalError`, which is a distinct, unrelated type). Any other OperationalError, or
    the last attempt, re-raises immediately.
    """
    for attempt in range(_LOCK_RETRIES):  # pragma: no branch - returns, raises or retries
        try:
            with db.atomic():
                action()
        except peewee.OperationalError as error:
            if not ("locked" in str(error).lower() and attempt < _LOCK_RETRIES - 1):
                raise
            logger.warning("%s: DB locked, retrying (%d)", name, attempt + 1)
            time.sleep(_LOCK_BACKOFF_S)
        else:
            return


def run_migrations(db: MigrationDatabase) -> list[str]:
    """Bring `db` up to the latest schema version, applying only pending migrations.

    Returns the names of the migrations actually applied (empty when the schema is already current).
    Takes a consistent pre-migration backup only when there is at least one pending migration. Each
    migration (and the schema_version table setup itself) runs in its own transaction, retried on a
    B5-style lock — a failure leaves the version at the last fully-applied migration, never a torn
    state.
    """
    version = current_version(db)
    pending = [(number, name, migrate) for number, name, migrate in MIGRATIONS if number > version]
    if not pending:
        return []
    _backup(db)
    _run_locked(db, "schema_version_table", lambda: _ensure_schema_version_table(db))
    applied: list[str] = []
    for number, name, migrate in pending:

        def _apply(
            number: int = number, migrate: Callable[[MigrationDatabase], None] = migrate
        ) -> None:
            migrate(db)
            db.execute_sql("UPDATE schema_version SET version = ?", (number,))

        _run_locked(db, name, _apply)
        applied.append(name)
    return applied
