import json
from unittest.mock import AsyncMock, patch

import pytest


def test_parse_args_sync():
    from moonlighter.tracking.cli import parse_args

    assert parse_args(["sync"]).command == "sync"


def test_parse_args_with_no_command_emits_usage_error_json_on_stdout(capsys):
    from moonlighter.tracking.cli import parse_args

    with pytest.raises(SystemExit) as exc:
        parse_args([])
    assert exc.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "usage_error"


async def test_run_sync_exits_0_with_the_updates_as_json(tmp_db):
    from moonlighter.tracking import cli

    updates = [
        {
            "job_id": 7,
            "status_advanced": True,
            "company": "Acme",
            "title": "T",
            "type": "interview",
            "stage": None,
            "match_type": "ref",
            "summary": "",
        }
    ]
    with (
        patch.object(cli, "bootstrap", return_value=({"email": {}}, {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "sync_responses", new=AsyncMock(return_value=updates)),
    ):
        payload, code = await cli._run(cli.parse_args(["sync"]))
    assert (payload["kind"], code) == ("synced", 0)
    assert payload["updates"] == updates
    json.dumps(payload)


async def test_run_sync_with_no_updates_exits_1(tmp_db):
    from moonlighter.tracking import cli

    with (
        patch.object(cli, "bootstrap", return_value=({"email": {}}, {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "sync_responses", new=AsyncMock(return_value=[])),
    ):
        payload, code = await cli._run(cli.parse_args(["sync"]))
    assert (payload, code) == ({"kind": "synced", "updates": []}, 1)


def test_run_via_run_classifies_a_missing_gmail_token_as_an_expected_failure(tmp_db, capsys):
    # Measured: moonlighter-email sync with no Gmail token lands on exit 3
    # with a full traceback today. A missing credential is a routine,
    # anticipated failure -- exit 1, kind "expected_failure" -- not a crash.
    # Goes THROUGH run() with the real module tuple, per the review brief.
    from moonlighter.core.cli import run
    from moonlighter.tracking import cli
    from moonlighter.tracking.gmail_client import GmailAuthError

    with (
        patch.object(cli, "bootstrap", return_value=({"email": {}}, {})),
        patch.object(cli, "make_caller", return_value=object()),
        patch.object(cli, "sync_responses", new=AsyncMock(side_effect=GmailAuthError("no token"))),
    ):
        args = cli.parse_args(["sync"])
        code = run(lambda: cli._run(args), expected=cli.EXPECTED_FAILURES)
    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "expected_failure"
    assert out["type"] == "GmailAuthError"


async def test_run_register_exits_0_and_prints_the_alias(tmp_db):
    from moonlighter.tracking import cli
    from moonlighter.tracking.register import RegisterKind, RegisterResult

    r = RegisterResult(
        RegisterKind.REGISTERED,
        7,
        application_id=1,
        status="submitted",
        email_ref="ab12cd34",
        alias="jane+ab12cd34@example.com",
    )
    with (
        patch.object(
            cli, "bootstrap", return_value=({"email": {"address": "jane@example.com"}}, {})
        ),
        patch.object(cli, "register_application", return_value=r),
    ):
        payload, code = await cli._run(cli.parse_args(["register", "7"]))
    assert (payload["kind"], payload["alias"], code) == (
        "registered",
        "jane+ab12cd34@example.com",
        0,
    )


async def test_run_register_unknown_job_exits_1(tmp_db):
    from moonlighter.tracking import cli
    from moonlighter.tracking.register import RegisterKind, RegisterResult

    r = RegisterResult(RegisterKind.JOB_NOT_FOUND, 7, error="Job 7 not found.")
    with (
        patch.object(cli, "bootstrap", return_value=({}, {})),
        patch.object(cli, "register_application", return_value=r),
    ):
        payload, code = await cli._run(cli.parse_args(["register", "7"]))
    assert (payload["kind"], code) == ("job_not_found", 1)


def test_email_keeps_its_grammar_and_gains_doctor():
    from moonlighter.tracking.cli import parse_args

    assert parse_args(["doctor"]).command == "doctor"
    assert parse_args(["sync"]).command == "sync"


async def test_email_doctor_returns_the_doctor_payload(tmp_db):
    from moonlighter.tracking import cli

    with patch.object(cli, "doctor_payload", return_value=({"kind": "doctor"}, 0)):
        payload, code = await cli._run(cli.parse_args(["doctor"]))
    assert (payload, code) == ({"kind": "doctor"}, 0)


def test_email_help_carries_the_slice_epilog(capsys):
    from moonlighter.tracking.cli import parse_args

    with pytest.raises(SystemExit) as exc:
        parse_args(["--help"])
    assert exc.value.code == 0
    assert "installed:" in capsys.readouterr().out
