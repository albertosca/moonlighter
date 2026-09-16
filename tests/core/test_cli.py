import json
from datetime import datetime

from moonlighter.core.config import ConfigError
from moonlighter.core.db import Job, init_db


def test_job_to_dict_projects_every_column_with_iso_datetimes(tmp_db):
    from moonlighter.core.cli import job_to_dict

    init_db()
    job = Job.create(
        source="greenhouse",
        company="Acme",
        title="Staff Engineer",
        url="https://boards.greenhouse.io/acme/jobs/1",
        score=8.5,
        status="new",
        posted_at=datetime(2026, 9, 1, 12, 0, 0),
    )
    d = job_to_dict(job)
    assert d["id"] == job.id
    assert d["company"] == "Acme"
    assert d["score"] == 8.5
    assert d["posted_at"] == "2026-09-01T12:00:00"
    assert d["closed_at"] is None
    # Every persisted column is present: a consumer never has to go back to the DB.
    for column in (
        "source",
        "title",
        "url",
        "location",
        "remote_type",
        "description",
        "score_notes",
        "caveats",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_source",
        "salary_notes",
        "status",
        "found_at",
    ):
        assert column in d


def test_emit_writes_exactly_one_json_line_to_stdout_and_returns_the_code(capsys):
    from moonlighter.core.cli import emit

    code = emit({"kind": "evaluated", "saved": []}, 0)
    out, err = capsys.readouterr()
    assert code == 0
    assert err == ""
    assert out.endswith("\n") and out.count("\n") == 1
    assert json.loads(out) == {"kind": "evaluated", "saved": []}


async def _ok():
    return {"kind": "evaluated"}, 0


async def _config_broken():
    raise ConfigError("unknown config key 'nope'")


async def _crash():
    raise ValueError("boom")


def test_run_drives_the_entry_and_returns_its_exit_code(capsys):
    from moonlighter.core.cli import run

    assert run(_ok) == 0
    assert json.loads(capsys.readouterr().out) == {"kind": "evaluated"}


def test_run_maps_a_config_error_to_json_on_stdout_and_exit_2(capsys):
    # The contract is JSON on stdout ALWAYS — a broken config must not turn
    # into a traceback on stderr that a script cannot parse.
    from moonlighter.core.cli import EXIT_USAGE, run

    assert run(_config_broken) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "config_error", "error": "unknown config key 'nope'"}


def test_run_maps_an_unexpected_exception_to_json_on_stdout_and_exit_3(capsys, caplog):
    # Anything that isn't a ConfigError (a DB error, a plain bug) still has to
    # leave stdout as one parseable JSON document — never an empty stdout with
    # a traceback on stderr and Python's default exit code 1, which would
    # collide with EXIT_NOTHING without being a deliberate mapping.
    from moonlighter.core.cli import EXIT_CRASH, run

    assert run(_crash) == EXIT_CRASH
    out = capsys.readouterr().out
    # stdout carries exactly the one JSON document and nothing else — no
    # traceback, no extra lines.
    assert out.endswith("\n") and out.count("\n") == 1
    assert json.loads(out) == {"kind": "error", "type": "ValueError", "error": "boom"}
    # The human-facing half: the traceback/message still reaches the log.
    # (Not asserting stderr is otherwise empty: moonlighter.core.log.setup()
    # is a process-wide, once-only side effect that other tests in the suite
    # may already have triggered, which would make a real Rich handler write
    # to actual stderr here too — that's independent of this test's contract.)
    assert "boom" in caplog.text


def test_bootstrap_loads_config_and_profile_and_inits_the_db(tmp_db, monkeypatch, tmp_path):
    from moonlighter.core import cli

    monkeypatch.setattr(cli, "load_config", lambda: {"score_threshold": 7.0})
    monkeypatch.setattr(cli, "validate_config", lambda c: None)
    monkeypatch.setattr(cli, "load_profile", lambda: {"name": "Jane"})
    monkeypatch.setattr(cli, "harden_permissions", lambda: [])
    config, profile = cli.bootstrap()
    assert config == {"score_threshold": 7.0}
    assert profile == {"name": "Jane"}
    Job.select().count()  # init_db ran: the table exists


def test_bootstrap_tolerates_a_missing_profile(tmp_db, monkeypatch):
    from moonlighter.core import cli

    def _missing():
        raise FileNotFoundError

    monkeypatch.setattr(cli, "load_config", lambda: {})
    monkeypatch.setattr(cli, "validate_config", lambda c: None)
    monkeypatch.setattr(cli, "load_profile", _missing)
    monkeypatch.setattr(cli, "harden_permissions", lambda: [])
    assert cli.bootstrap() == ({}, {})


def test_bootstrap_prints_permission_warnings_to_stderr_not_stdout(tmp_db, monkeypatch, capsys):
    from moonlighter.core import cli

    monkeypatch.setattr(cli, "load_config", lambda: {})
    monkeypatch.setattr(cli, "validate_config", lambda c: None)
    monkeypatch.setattr(cli, "load_profile", lambda: {})
    monkeypatch.setattr(cli, "harden_permissions", lambda: ["config.yaml was world-readable"])
    cli.bootstrap()
    out, err = capsys.readouterr()
    assert out == ""
    assert "world-readable" in err
