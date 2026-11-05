"""A config or profile edit reaches a running server on its next tool call, and a bad edit never replaces the last good file."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from moonlighter.app_context import refreshed_app_context
from moonlighter.discovery import archive
from moonlighter.discovery.archive import ArchiveResult
from moonlighter.mcp_tools import scanning
from moonlighter.server import lifespan, mcp

# ── config/profile edits reach a running server (2026-09-25) ──────────────────
# The server read config.yaml and profile.yaml once, at connect time. A config
# flag set mid-session (email.archive_all_classified) was silently ignored:
# sync_email_responses reported success, archived nothing, and marked the
# messages processed for good.


def _write(path, text, *, later_than=None):
    path.write_text(text)
    if later_than is not None:
        stamp = later_than.stat().st_mtime + 5
        os.utime(path, (stamp, stamp))


def _context_for(app_context):
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app_context))


async def test_a_config_edit_reaches_the_next_tool_call_without_reconnecting(
    temporary_database, monkeypatch, tmp_path
):

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    _write(config_path, "score_threshold: 7.0\n")
    service = AsyncMock(return_value=ArchiveResult())
    monkeypatch.setattr(archive, "archive_stale_jobs", service)
    api_caller = object()
    monkeypatch.setattr("moonlighter.app_context.make_caller", lambda config: api_caller)
    async with lifespan(mcp) as app_context:
        await scanning.archive_stale_jobs(context=_context_for(app_context))
        app_context.llm_caller = None
        _write(config_path, "score_threshold: 8.5\n", later_than=config_path)
        await scanning.archive_stale_jobs(context=_context_for(app_context))
    assert service.await_args_list[0].args[2]["score_threshold"] == 7.0
    assert service.await_args_list[1].args[2]["score_threshold"] == 8.5
    # The caller depends on llm_backend, so a config edit rebuilds it.
    assert app_context.llm_caller is api_caller


async def test_a_profile_edit_reaches_the_next_tool_call(temporary_database, monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with lifespan(mcp) as app_context:
        assert refreshed_app_context(_context_for(app_context)).profile["headline"] == "Before"
        _write(profile_path, "headline: After\n", later_than=profile_path)
        assert refreshed_app_context(_context_for(app_context)).profile["headline"] == "After"


async def test_an_unchanged_config_is_not_read_again(temporary_database, monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 7.0\n")
    async with lifespan(mcp) as app_context:
        config = app_context.config
        refreshed_app_context(_context_for(app_context))
        assert app_context.config is config


@pytest.mark.usefixtures("temporary_database")
async def test_an_invalid_config_edit_keeps_the_last_good_one_and_warns(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    _write(config_path, "score_threshold: 7.0\n")
    async with lifespan(mcp) as app_context:
        _write(config_path, "scan_concurrency: five\n", later_than=config_path)
        app = refreshed_app_context(_context_for(app_context))
    assert app.config["score_threshold"] == 7.0
    assert "config.yaml" in caplog.text


async def test_a_deleted_profile_becomes_empty(temporary_database, monkeypatch, tmp_path):
    """Unlike a deleted config, a deleted profile is a legitimate state: the server
    boots with {} when profile.yaml is absent, so a deletion mid-session means the same.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with lifespan(mcp) as app_context:
        profile_path.unlink()
        assert refreshed_app_context(_context_for(app_context)).profile == {}


@pytest.mark.usefixtures("temporary_database")
async def test_a_malformed_profile_edit_keeps_the_last_good_one_and_warns(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with lifespan(mcp) as app_context:
        _write(profile_path, "headline: [unclosed\n", later_than=profile_path)
        app = refreshed_app_context(_context_for(app_context))
    assert app.profile["headline"] == "Before"
    assert "profile.yaml" in caplog.text


@pytest.mark.parametrize(
    ("file_name", "bad_text"),
    [
        ("config.yaml", "- a\n- list\n"),
        ("config.yaml", ""),
        ("profile.yaml", "just a string\n"),
        ("profile.yaml", "- x\n"),
        ("profile.yaml", ""),
    ],
)
@pytest.mark.usefixtures("temporary_database")
async def test_an_edit_that_is_not_a_mapping_keeps_the_last_good_file(
    *, monkeypatch, tmp_path, caplog, file_name, bad_text
):
    """A list, a scalar, or an empty file (an editor that truncates, then writes)
    must not replace the settings: one tool call on defaults mid-write is the
    2026-09-25 class of bug.
    """
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 8.0\n")
    _write(tmp_path / "profile.yaml", "headline: Before\n")
    async with lifespan(mcp) as app_context:
        _write(tmp_path / file_name, bad_text, later_than=tmp_path / file_name)
        app = refreshed_app_context(_context_for(app_context))
    assert app.config["score_threshold"] == 8.0
    assert app.profile == {"headline": "Before"}
    assert file_name in caplog.text


@pytest.mark.usefixtures("temporary_database")
async def test_a_deleted_config_keeps_the_last_good_one(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 8.0\n")
    async with lifespan(mcp) as app_context:
        (tmp_path / "config.yaml").unlink()
        app = refreshed_app_context(_context_for(app_context))
    assert app.config["score_threshold"] == 8.0
    assert "config.yaml" in caplog.text
