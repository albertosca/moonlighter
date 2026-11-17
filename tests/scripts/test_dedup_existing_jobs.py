"""The backfill script: dry run by default, --apply only behind a backup it writes itself."""

import sqlite3
from contextlib import closing

import dedup_existing_jobs
import pytest

from moonlighter.core.db import Application, Job, init_db

TEXT = "We build Rails apps for payments. Remote in Brazil."


def _two_copies():
    init_db()
    first = Job.create(
        source="recruitee",
        company="Tether",
        title="Eng",
        url="https://x/1",
        description=TEXT,
        score=8.0,
        score_notes="good fit",
    )
    second = Job.create(
        source="recruitee",
        company="Tether",
        title="Eng",
        url="https://x/1-9",
        description=TEXT,
        score=8.0,
        score_notes="good fit",
    )
    return first, second


def test_the_dry_run_lists_the_groups_and_writes_nothing(temporary_database, capsys):
    first, second = _two_copies()
    assert dedup_existing_jobs.main([]) == 0
    output = capsys.readouterr().out
    assert f"kept #{first.id} Tether/Eng (8.0) ← copies #{second.id}" in output
    assert "1 group(s), 1 copy(ies). Dry run: nothing changed" in output
    assert Job.get_by_id(second.id).duplicate_of_id is None


def test_apply_requires_a_backup(temporary_database, capsys):
    _two_copies()
    assert dedup_existing_jobs.main(["--apply"]) == 2
    assert "--apply requires --backup PATH" in capsys.readouterr().err


def test_apply_refuses_to_overwrite_a_backup(temporary_database, tmp_path, capsys):
    _two_copies()
    existing = tmp_path / "taken.db"
    existing.write_text("")
    assert dedup_existing_jobs.main(["--apply", "--backup", str(existing)]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def test_apply_refuses_a_backup_in_a_missing_directory(temporary_database, tmp_path, capsys):
    _two_copies()
    target = tmp_path / "missing" / "backup.db"
    assert dedup_existing_jobs.main(["--apply", "--backup", str(target)]) == 2
    assert f"backup directory does not exist: {target.parent}" in capsys.readouterr().err
    assert Job.select().where(Job.duplicate_of.is_null(is_null=False)).count() == 0


def test_apply_writes_the_backup_then_archives_the_copies(temporary_database, tmp_path):
    first, second = _two_copies()
    Application.create(job=second, status="submitted")
    third = Job.create(
        source="recruitee", company="Tether", title="Eng", url="https://x/1-10", description=TEXT
    )
    backup = tmp_path / "before.db"
    assert dedup_existing_jobs.main(["--apply", "--backup", str(backup)]) == 0
    with closing(sqlite3.connect(backup)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM job").fetchone() == (3,)
    for copy in (first, third):
        stored = Job.get_by_id(copy.id)
        assert (stored.status, stored.duplicate_of_id) == ("archived", second.id)
        assert stored.score_notes.startswith(f"duplicate of #{second.id}")
    assert Job.get_by_id(first.id).score_notes == f"duplicate of #{second.id} — good fit"
    assert Job.get_by_id(second.id).duplicate_of_id is None


@pytest.fixture
def mismatched_backup(monkeypatch):
    monkeypatch.setattr(dedup_existing_jobs, "_count_jobs", lambda _path: -1)


@pytest.mark.usefixtures("temporary_database", "mismatched_backup")
def test_a_backup_that_does_not_match_stops_before_writing(tmp_path, capsys):
    _, second = _two_copies()
    assert dedup_existing_jobs.main(["--apply", "--backup", str(tmp_path / "b.db")]) == 3
    assert "backup does not match" in capsys.readouterr().err
    assert Job.get_by_id(second.id).duplicate_of_id is None


@pytest.mark.parametrize("arguments", [[], ["--apply", "--backup", "unused"]])
def test_nothing_to_do_says_so(temporary_database, capsys, arguments):
    init_db()
    assert dedup_existing_jobs.main(arguments) == 0
    assert "No duplicate groups." in capsys.readouterr().out
