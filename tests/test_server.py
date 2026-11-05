"""The composition root: the registered tool surface, the subcommand dispatch and the startup wiring."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import moonlighter.core.log as log_mod
from moonlighter.core.db import init_db
from moonlighter.mcp_tools.applications import get_pipeline
from moonlighter.server import _dispatch, mcp
from moonlighter.startup import StartupWarning
from tests._context import make_test_context
from tests._fresh_import import import_server_afresh
from tests.mcp_tools._records import create_application, create_job


def test_importing_the_server_builds_it_without_an_api_key(monkeypatch):
    """A fresh import of the server builds it with no ANTHROPIC_API_KEY set.

    The startup checks run in the lifespan, not at import, so a missing key must
    not stop the module from loading: `mcp` exists and carries the server's name.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    module = import_server_afresh(monkeypatch)
    assert module.mcp.name == "moonlighter"


def test_startup_warning_level_values():
    error_warning = StartupWarning(level="error", message="msg")
    warn_warning = StartupWarning(level="warn", message="msg")
    assert error_warning.level == "error"
    assert warn_warning.level == "warn"


def test_mcp_server_initializes_logging():
    """Importing the server module must not blow up and must have logging set up."""
    # if the module was already imported, _initialized should be True
    assert log_mod._initialized is True


def test_dispatch_with_no_argv_returns_none_so_the_server_starts():
    assert _dispatch([]) is None


def test_dispatch_help_prints_usage_and_returns_0(capsys):
    assert _dispatch(["--help"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: moonlighter")


def test_dispatch_short_help_flag_also_works(capsys):
    assert _dispatch(["-h"]) == 0
    assert capsys.readouterr().out.startswith("usage: moonlighter")


def test_dispatch_doctor_emits_the_doctor_payload_and_its_exit_code(capsys):
    with patch("moonlighter.server.doctor_payload", return_value=({"kind": "doctor"}, 1)):
        code = _dispatch(["doctor"])
    assert code == 1
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert json.loads(out) == {"kind": "doctor"}


def test_dispatch_unknown_word_returns_none_and_falls_through_to_the_server():
    # Unrecognized words are not this dispatcher's business -- they must not
    # be swallowed, so the caller's existing "start the server" fallback still
    # runs unchanged for any argv this function does not understand.

    assert _dispatch(["serve-me"]) is None


async def test_tools_list_surface_is_pinned(snapshot_text):
    """Names, order, descriptions, input schemas and annotations of every tool, as a
    client sees them in tools/list.
    """
    tools = await mcp.list_tools()
    dump = [tool.model_dump(mode="json", by_alias=True) for tool in tools]
    snapshot_text(json.dumps(dump, indent=2, sort_keys=True, ensure_ascii=False), "tools_list")


async def test_get_pipeline_whole_text_is_pinned(temporary_database, monkeypatch, snapshot_text):
    init_db()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stripe = create_job(temporary_database, url="https://x.com/pin1", company="Stripe")
    linear = create_job(
        temporary_database, url="https://x.com/pin2", company="Linear", title="Designer"
    )
    create_application(
        stripe,
        status="submitted",
        applied_at=datetime(2026, 3, 5),  # noqa: DTZ001 - the models store naive local timestamps, so the test builds one the same way
        next_action="follow up em 2026-06-01",
    )
    create_application(linear, status="interviews")

    config = {"llm_backend": "api", "browser_path": "/nonexistent/browser"}
    with patch("moonlighter.startup.moonlighter_home", return_value=Path("/nonexistent-home")):
        result = await get_pipeline(context=make_test_context(config=config, profile={}))
    snapshot_text(result, "get_pipeline")
