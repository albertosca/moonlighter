"""bootstrap loads the config and profile, inits the database, and prints permission warnings on stderr only."""

from moonlighter.core import cli
from moonlighter.core.db import Job


def test_bootstrap_loads_config_and_profile_and_inits_the_db(
    temporary_database, monkeypatch, tmp_path
):
    monkeypatch.setattr(cli, "load_config", lambda: {"score_threshold": 7.0})
    monkeypatch.setattr(cli, "validate_config", lambda config: None)
    monkeypatch.setattr(cli, "load_profile", lambda: {"name": "Jane"})
    monkeypatch.setattr(cli, "harden_permissions", list)
    config, profile = cli.bootstrap()
    assert config == {"score_threshold": 7.0}
    assert profile == {"name": "Jane"}
    Job.select().count()  # init_db ran: the table exists


def test_bootstrap_tolerates_a_missing_profile(temporary_database, monkeypatch):
    def _missing():
        raise FileNotFoundError

    monkeypatch.setattr(cli, "load_config", dict)
    monkeypatch.setattr(cli, "validate_config", lambda config: None)
    monkeypatch.setattr(cli, "load_profile", _missing)
    monkeypatch.setattr(cli, "harden_permissions", list)
    assert cli.bootstrap() == ({}, {})


def test_bootstrap_prints_permission_warnings_to_stderr_not_stdout(
    temporary_database, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "load_config", dict)
    monkeypatch.setattr(cli, "validate_config", lambda config: None)
    monkeypatch.setattr(cli, "load_profile", dict)
    monkeypatch.setattr(cli, "harden_permissions", lambda: ["config.yaml was world-readable"])
    cli.bootstrap()
    out, error_output = capsys.readouterr()
    assert out == ""
    assert "world-readable" in error_output
