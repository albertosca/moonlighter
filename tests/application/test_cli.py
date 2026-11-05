import json
import sys
from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.application import cli
from moonlighter.application.commands import bootstrap_cv as bootstrap_cv_command
from moonlighter.application.commands import doctor as doctor_command
from moonlighter.application.cvgen.bootstrap_error import BootstrapError
from moonlighter.core.cli import run


def test_parse_args_prepare_with_optional_paste():
    parsed_arguments = cli.parse_args(["prepare", "42"])
    assert (parsed_arguments.command, parsed_arguments.job_id, parsed_arguments.paste) == (
        "prepare",
        42,
        None,
    )
    assert cli.parse_args(["prepare", "42", "--paste", "-"]).paste == "-"


def test_parse_args_prepare_with_a_non_int_job_id_emits_usage_error_json_on_stdout(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["prepare", "not-a-number"])
    assert exit_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "usage_error"


def test_run_via_run_classifies_a_missing_paste_file_as_a_usage_error(temporary_database, capsys):
    # Measured: moonlighter-apply prepare 1 --paste /nonexistent lands on exit
    # 3 (FileNotFoundError) today. A bad --paste path is a bad argument, not
    # a crash -- exit 2, kind "usage_error". Goes THROUGH run() with the real
    # module tuple, per the review brief.
    with patch.object(cli, "bootstrap", return_value=({}, {})):
        parsed_arguments = cli.parse_args(["prepare", "42", "--paste", "/nonexistent/file"])
        code = run(lambda: cli._run(parsed_arguments), usage=cli.USAGE_ERRORS)
    assert code == 2
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "usage_error"
    assert out["type"] == "FileNotFoundError"


def test_parse_args_prepare_requires_exactly_one_of_job_id_and_url(capsys):
    for argv in (["prepare"], ["prepare", "42", "--url", "https://x"]):
        with pytest.raises(SystemExit) as exit_info:
            cli.parse_args(argv)
        assert exit_info.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


def test_parse_args_prepare_with_url_and_company_title_overrides():
    parsed_arguments = cli.parse_args(
        ["prepare", "--url", "u", "--company", "Acme", "--title", "Eng"]
    )
    assert (parsed_arguments.url, parsed_arguments.company, parsed_arguments.title) == (
        "u",
        "Acme",
        "Eng",
    )


def test_parse_args_prepare_company_or_title_without_url_is_a_usage_error(capsys):
    for argv in (
        ["prepare", "42", "--company", "Acme"],
        ["prepare", "42", "--title", "Eng"],
    ):
        with pytest.raises(SystemExit) as exit_info:
            cli.parse_args(argv)
        assert exit_info.value.code == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "usage_error"


def test_apply_keeps_its_grammar_and_gains_doctor():
    assert cli.parse_args(["doctor"]).command == "doctor"
    assert cli.parse_args(["prepare", "42"]).command == "prepare"


def test_apply_help_carries_the_slice_epilog(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--help"])
    assert exit_info.value.code == 0
    assert "installed:" in capsys.readouterr().out


def test_bootstrap_cv_subcommand_reports_a_bootstrap_error_as_expected_failure(monkeypatch, capsys):
    # _run() itself never classifies its own exceptions -- that's run()'s job
    # (see core/cli.py's docstring and this slice's other expected/usage-error
    # test, test_run_via_run_classifies_a_missing_paste_file_as_a_usage_error,
    # a few tests up), so this goes THROUGH run() with EXPECTED_ERRORS, same
    # as that sibling test does for USAGE_ERRORS -- not through a bare
    # `await cli._run(...)`, which would let the BootstrapError propagate
    # uncaught instead of returning a (payload, code) tuple.
    monkeypatch.setattr(cli, "bootstrap", lambda: ({}, {"name": "Jane"}))

    async def _fake_bootstrap(profile, config, caller, *, force=False):
        raise BootstrapError("a pool already exists")

    monkeypatch.setattr(bootstrap_cv_command, "bootstrap_cv_pool", _fake_bootstrap)
    parsed_arguments = cli.parse_args(["bootstrap-cv"])
    code = run(lambda: cli._run(parsed_arguments), expected=cli.EXPECTED_ERRORS)
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "expected_failure"


def test_parse_args_usage_errors_carry_the_message_the_operator_reads(capsys):
    expectations = (
        (["prepare"], "prepare takes exactly one of JOB_ID or --url"),
        (["prepare", "42", "--url", "https://x"], "prepare takes exactly one of JOB_ID or --url"),
        (
            ["prepare", "42", "--company", "Acme"],
            "--company and --title are only meaningful with --url",
        ),
        (
            ["prepare", "42", "--title", "Eng"],
            "--company and --title are only meaningful with --url",
        ),
    )
    for argv, message in expectations:
        with pytest.raises(SystemExit):
            cli.parse_args(argv)
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"kind": "usage_error", "error": message}


def test_parse_args_reads_sys_argv_when_given_no_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moonlighter-apply", "doctor", "--online"])
    parsed_arguments = cli.parse_args()
    assert (parsed_arguments.command, parsed_arguments.online) == ("doctor", True)


async def test_apply_doctor_never_calls_bootstrap_even_online(temporary_database):
    with (
        patch.object(cli, "bootstrap") as bootstrap_spy,
        patch.object(doctor_command, "doctor_payload", return_value=({"kind": "doctor"}, 0)),
        patch.object(doctor_command, "link_report", AsyncMock(return_value=[])),
    ):
        await cli._run(cli.parse_args(["doctor"]))
        await cli._run(cli.parse_args(["doctor", "--online"]))
    bootstrap_spy.assert_not_called()
