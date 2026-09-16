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
