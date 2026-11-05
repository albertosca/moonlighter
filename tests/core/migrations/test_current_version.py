"""current_version reads 0 from a database with no schema_version table or with an empty one, and writes nothing."""

from moonlighter.core.migrations import current_version

from tests.core.migrations.unmigrated_db import fresh_db


def test_current_version_is_zero_before_any_migration(tmp_path, open_dbs):
    db = fresh_db(tmp_path / "t.db", open_dbs)
    assert current_version(db) == 0


def test_current_version_is_zero_when_table_exists_but_empty(tmp_path, open_dbs):
    """Defensive branch: `schema_version` exists (e.g. a torn prior run that
    created the table but never got to seed it) but holds no row. Reading it
    must still return 0, not raise — and `current_version` must not write
    anything to fix it up (it stays read-only).
    """
    db = fresh_db(tmp_path / "t.db", open_dbs)
    db.execute_sql("CREATE TABLE schema_version (version INTEGER NOT NULL)")

    assert current_version(db) == 0
    assert db.execute_sql("SELECT * FROM schema_version").fetchone() is None
