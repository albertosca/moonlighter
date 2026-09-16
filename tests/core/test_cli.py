import json
from datetime import datetime
from unittest.mock import patch

import pytest
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


class _NoToken(Exception):
    pass


class _BadArg(Exception):
    pass


async def _no_token():
    raise _NoToken("no token")


async def _bad_arg():
    raise _BadArg("bad path")


def test_run_classifies_an_expected_failure_as_exit_1_not_a_crash(capsys):
    # A routine, anticipated failure (missing credential, no data yet) is not
    # a bug: it must not land on EXIT_CRASH with a traceback the caller reads
    # as "something broke". expected= is how a slice's cli.py declares which
    # exceptions are routine for IT, without core/cli.py naming them.
    from moonlighter.core.cli import EXIT_NOTHING, run

    assert run(_no_token, expected=(_NoToken,)) == EXIT_NOTHING
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "expected_failure", "type": "_NoToken", "error": "no token"}


def test_run_classifies_a_usage_error_as_exit_2(capsys):
    from moonlighter.core.cli import EXIT_USAGE, run

    assert run(_bad_arg, usage=(_BadArg,)) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out == {"kind": "usage_error", "type": "_BadArg", "error": "bad path"}


def test_run_usage_takes_priority_over_expected_when_both_match(capsys):
    # Order of clauses: ConfigError -> usage -> expected -> crash. A slice
    # could plausibly list the same exception type in both tuples; usage wins,
    # since it is checked first.
    from moonlighter.core.cli import EXIT_USAGE, run

    assert run(_bad_arg, expected=(_BadArg,), usage=(_BadArg,)) == EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "usage_error"


def test_run_default_expected_and_usage_are_empty_and_match_nothing(capsys):
    # An empty tuple in an except clause matches nothing -- run() with no
    # expected=/usage= behaves exactly as before this feature existed.
    from moonlighter.core.cli import EXIT_CRASH, run

    assert run(_crash) == EXIT_CRASH
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "error"


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


def test_json_argument_parser_error_emits_usage_error_json_on_stdout_and_exits_2(capsys):
    # argparse's default .error() writes usage prose to stderr and NOTHING to
    # stdout -- a shell script that always parses stdout as JSON gets zero
    # bytes on a bad flag. JsonArgumentParser must still leave stdout carrying
    # exactly the contract's one JSON document.
    from moonlighter.core.cli import JsonArgumentParser

    parser = JsonArgumentParser(prog="x")
    parser.add_argument("--flag")
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--bogus"])
    assert exc.value.code == 2
    out, err = capsys.readouterr()
    assert out.endswith("\n") and out.count("\n") == 1
    payload = json.loads(out)
    assert payload["kind"] == "usage_error"
    # argparse's own message names the unrecognized argument -- assert the
    # contract (kind + presence), not argparse's exact wording.
    assert "bogus" in payload["error"]
    assert err != ""  # usage prose still goes to stderr, unchanged


def test_json_argument_parser_help_still_exits_0_on_stdout(capsys):
    # --help must keep going through argparse's own default path (stdout,
    # exit 0) -- JsonArgumentParser only changes .error(), never .exit()/-h.
    from moonlighter.core.cli import JsonArgumentParser

    parser = JsonArgumentParser(prog="x")
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    out, _err = capsys.readouterr()
    assert "usage" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


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


def test_doctor_payload_reports_paths_slices_and_a_valid_config(monkeypatch, tmp_path):
    # No tmp_db here: doctor_payload() only checks db path existence, never
    # opens the DB, and tmp_db's MOONLIGHTER_DB_PATH override would shadow the
    # MOONLIGHTER_HOME set below, breaking the "path ends in moonlighter.db"
    # assertion.
    import json

    from moonlighter.core import cli

    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = cli.doctor_payload()
    json.dumps(payload)
    assert code == 0
    assert payload["kind"] == "doctor"
    assert payload["home"] == str(tmp_path)
    assert payload["config"] == {
        "path": str(tmp_path / "config.yaml"),
        "exists": True,
        "valid": True,
        "error": None,
    }
    assert (
        payload["profile"]["path"] == str(tmp_path / "profile.yaml")
        and payload["profile"]["exists"] is False
    )
    assert payload["db"]["path"].endswith("moonlighter.db")
    assert set(payload["slices"]) == {"scan", "apply", "email", "full"}
    assert payload["commands"] == sorted(payload["commands"])
    assert {c["name"] for c in payload["capabilities"]["live"]} >= {"discovery"}


def test_doctor_payload_reports_an_invalid_config_and_exits_1(tmp_db, monkeypatch, tmp_path):
    from moonlighter.core import cli

    (tmp_path / "config.yaml").write_text("nope: 1\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = cli.doctor_payload()
    assert code == 1
    assert payload["config"]["valid"] is False
    assert "unknown config key 'nope'" in payload["config"]["error"]


def test_doctor_payload_reports_a_missing_config_and_exits_1(tmp_db, monkeypatch, tmp_path):
    from moonlighter.core import cli

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = cli.doctor_payload()
    assert (payload["config"]["exists"], code) == (False, 1)


def test_doctor_payload_live_and_missing_capabilities_share_the_same_keys(
    tmp_db, monkeypatch, tmp_path
):
    # One payload, two object shapes was the bug: live[] carried name/commands
    # /summary, missing[] carried name/needs/summary. A consumer keying off
    # either list the same way would KeyError on the other. Both now carry
    # name, needs (sorted), commands (list), summary -- and missing[] alone
    # also carries needs_install, the subset of needs not yet installed.
    from moonlighter.core import cli

    (tmp_path / "config.yaml").write_text("score_threshold: 7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    with patch(
        "moonlighter.core.cli.installed_slices",
        return_value={"scan": True, "apply": False, "email": False, "full": False},
    ):
        payload, _code = cli.doctor_payload()

    live_by_name = {c["name"]: c for c in payload["capabilities"]["live"]}
    missing_by_name = {c["name"]: c for c in payload["capabilities"]["missing"]}

    assert live_by_name["discovery"] == {
        "name": "discovery",
        "needs": ["scan"],
        "commands": ["moonlighter-scan"],
        "summary": "scan company boards and portals, score postings, archive closed ones",
    }
    assert missing_by_name["sheets"] == {
        "name": "sheets",
        "needs": ["apply"],
        "commands": ["moonlighter-apply prepare"],
        "summary": "compose a paste-ready application sheet, from a job id or straight from a URL",
        "needs_install": ["apply"],
    }
    # scan-to-sheet needs {scan, apply}; scan is already installed, so only
    # apply is what still needs installing.
    assert missing_by_name["scan-to-sheet"]["needs"] == ["apply", "scan"]
    assert missing_by_name["scan-to-sheet"]["needs_install"] == ["apply"]


def test_doctor_payload_reports_a_malformed_yaml_config_instead_of_crashing(
    tmp_db, monkeypatch, tmp_path
):
    # load_config() reaches yaml.safe_load() before validate_config() ever
    # runs -- a syntax error there is a yaml.YAMLError, not a ConfigError, and
    # doctor_payload() must still report it as JSON instead of letting it
    # escape as a traceback (doctor's whole point is to be usable on a
    # broken install).
    from moonlighter.core import cli

    (tmp_path / "config.yaml").write_text("score_threshold: [7.0\n")
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    payload, code = cli.doctor_payload()
    assert code == 1
    assert payload["config"]["valid"] is False
    assert payload["config"]["error"] is not None
    error_lower = payload["config"]["error"].lower()
    assert "yaml" in error_lower or "pars" in error_lower or "scan" in error_lower


def test_doctor_payload_reports_an_unreadable_config_instead_of_crashing(
    tmp_db, monkeypatch, tmp_path
):
    # A chmod-000 config.yaml makes read_text() raise PermissionError, which
    # is neither a ConfigError nor a yaml.YAMLError -- doctor_payload() must
    # catch it too.
    import os

    from moonlighter.core import cli

    config_path = tmp_path / "config.yaml"
    config_path.write_text("score_threshold: 7.0\n")
    config_path.chmod(0o000)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    try:
        if os.access(config_path, os.R_OK):
            pytest.skip("running as a user that can read a chmod-000 file (e.g. root)")
        payload, code = cli.doctor_payload()
        assert code == 1
        assert payload["config"]["valid"] is False
        assert "permission" in payload["config"]["error"].lower()
    finally:
        config_path.chmod(0o644)
