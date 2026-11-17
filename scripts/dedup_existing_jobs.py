"""Archive the stored copies of one posting against the row that is kept.

Dry run by default: lists each group (kept row and copies) and the totals.
With --apply it first writes an SQLite online backup to --backup PATH (a new
file), checks that the backup holds as many jobs as the live database, and
only then archives the copies, each with duplicate_of set to the kept row.

The kept row is the one with an application, else the highest score, else the
lowest id. A row with an application is never archived as a copy.

Usage:
    uv run python scripts/dedup_existing_jobs.py [--apply --backup PATH]
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moonlighter.core.db import Application, Job, db, db_path, init_db
from moonlighter.core.duplicates import DuplicateGroup, group_duplicates

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BACKUP_MISMATCH = 3


def _parse(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="archive the copies (needs --backup)")
    parser.add_argument("--backup", type=Path, help="new file the database is copied to first")
    return parser.parse_args(arguments)


def _describe(group: DuplicateGroup) -> str:
    kept = group.kept
    copies = ", ".join(f"#{copy.id}" for copy in group.copies)
    return f"kept #{kept.id} {kept.company}/{kept.title} ({kept.score}) ← copies {copies}"


def _count_jobs(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT COUNT(*) FROM job").fetchone()
    return int(row[0])


def _write_backup(target: Path) -> None:
    # A consistent online backup (not a hot cp), the way migration_runner takes one.
    with closing(sqlite3.connect(db_path())) as live, closing(sqlite3.connect(target)) as copy:
        live.backup(copy)


def _archive(groups: list[DuplicateGroup]) -> None:
    with db.atomic():
        for group in groups:
            for copy in group.copies:
                note = f"duplicate of #{group.kept.id}"
                copy.status = "archived"
                copy.duplicate_of = group.kept.id
                copy.score_notes = f"{note} — {copy.score_notes}" if copy.score_notes else note
                copy.save()


def _usage_error(arguments: argparse.Namespace) -> str | None:
    if arguments.backup is None:
        return "--apply requires --backup PATH"
    if arguments.backup.exists():
        return f"refusing to overwrite {arguments.backup}"
    return None


def _apply(arguments: argparse.Namespace, groups: list[DuplicateGroup]) -> int:
    error = _usage_error(arguments)
    if error is not None:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    _write_backup(arguments.backup)
    if _count_jobs(arguments.backup) != Job.select().count():
        print(f"backup does not match the live database: {arguments.backup}", file=sys.stderr)
        return EXIT_BACKUP_MISMATCH
    _archive(groups)
    print(f"Archived. Backup: {arguments.backup}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the backfill; the exit code says what happened."""
    arguments = _parse(sys.argv[1:] if argv is None else argv)
    init_db()
    applied_job_ids = {application.job_id for application in Application.select()}
    groups = group_duplicates(list(Job.select().order_by(Job.id)), applied_job_ids)
    if not groups:
        print("No duplicate groups.")
        return EXIT_OK
    for group in groups:
        print(_describe(group))
    copies = sum(len(group.copies) for group in groups)
    print(f"\n{len(groups)} group(s), {copies} copy(ies).", end=" ")
    if not arguments.apply:
        print("Dry run: nothing changed (--apply --backup PATH to archive).")
        return EXIT_OK
    print()
    return _apply(arguments, groups)


if __name__ == "__main__":
    sys.exit(main())
