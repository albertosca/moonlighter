import json
from unittest.mock import AsyncMock, patch


def test_parse_args_sync():
    from moonlighter.tracking.cli import parse_args

    assert parse_args(["sync"]).command == "sync"


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
