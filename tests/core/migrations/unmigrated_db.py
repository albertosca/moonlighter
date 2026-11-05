"""The database the migration tests start from: the base tables, none of the migrated columns, no schema_version."""

from peewee import SqliteDatabase


def fresh_db(path, open_dbs, timeout=None):
    """A DB with the base tables (as init_db would create them) but none of
    the three columns the migrations add, and no schema_version table.

    `timeout` is forwarded to `sqlite3.connect` via peewee (default lets
    sqlite busy-wait up to 5s before raising, which the genuine-lock tests
    override to 0 so a lock raises immediately and the test stays fast)."""
    db = (
        SqliteDatabase(str(path), timeout=timeout)
        if timeout is not None
        else SqliteDatabase(str(path))
    )
    db.connect()
    open_dbs.append(db)
    db.execute_sql("CREATE TABLE application (id INTEGER PRIMARY KEY, job_id INTEGER)")
    db.execute_sql("CREATE TABLE job (id INTEGER PRIMARY KEY)")
    return db
