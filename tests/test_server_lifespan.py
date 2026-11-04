import pytest
from moonlighter.core.config.errors import ConfigError
from moonlighter.server import AppContext, lifespan, mcp


async def test_lifespan_yields_populated_appcontext(temporary_database):
    async with lifespan(mcp) as app_context:
        assert isinstance(app_context, AppContext)
        assert isinstance(app_context.config, dict)
        assert app_context.llm_caller is not None
        assert isinstance(app_context.startup_warnings, list)


async def test_lifespan_rejects_invalid_config(temporary_database, monkeypatch):
    import moonlighter.server as server

    bad = {"scan_concurrency": "five"}  # will fail validate_config
    monkeypatch.setattr(server, "load_config", lambda: bad)
    with pytest.raises(ConfigError):
        async with lifespan(mcp):
            pass  # must raise before yielding


async def test_lifespan_prints_permission_warnings(temporary_database, monkeypatch, capsys):
    import moonlighter.server as server

    monkeypatch.setattr(server, "harden_permissions", lambda: ["could not chmod ~/.moonlighter"])
    async with lifespan(mcp) as app_context:
        assert app_context.permission_warnings == ["could not chmod ~/.moonlighter"]
    assert "could not chmod ~/.moonlighter" in capsys.readouterr().err


def test_importing_server_has_no_side_effects(monkeypatch):
    import importlib
    import sys

    calls: list[str] = []
    import moonlighter.core.db as db
    from moonlighter.core import log
    from moonlighter.core.config import loading, permissions

    monkeypatch.setattr(
        loading,
        "load_config",
        lambda *positional_arguments, **keyword_arguments: calls.append("load_config") or {},
    )
    monkeypatch.setattr(
        db, "init_db", lambda *positional_arguments, **keyword_arguments: calls.append("init_db")
    )
    monkeypatch.setattr(
        permissions,
        "harden_permissions",
        lambda *positional_arguments, **keyword_arguments: calls.append("harden") or [],
    )
    monkeypatch.setattr(
        log,
        "setup",
        lambda *positional_arguments, **keyword_arguments: calls.append("setup_logging"),
    )
    # Through monkeypatch, not a bare sys.modules.pop: the re-imported copy is
    # bound to the lambda load_config above, and a bare pop left it in
    # sys.modules AND as the moonlighter package's `server` attribute (what
    # `import moonlighter.server as server` resolves to) for every later test.
    import moonlighter

    monkeypatch.setattr(moonlighter, "server", sys.modules["moonlighter.server"])
    monkeypatch.delitem(sys.modules, "moonlighter.server")
    importlib.import_module("moonlighter.server")
    assert calls == []  # importing the server must not load config / init db / harden perms


# ── config/profile edits reach a running server (2026-09-25) ──────────────────
# The server read config.yaml and profile.yaml once, at connect time. A config
# flag set mid-session (email.archive_all_classified) was silently ignored:
# sync_email_responses reported success, archived nothing, and marked the
# messages processed for good.


def _write(path, text, *, later_than=None):
    import os

    path.write_text(text)
    if later_than is not None:
        stamp = later_than.stat().st_mtime + 5
        os.utime(path, (stamp, stamp))


def _context_for(app_context):
    from types import SimpleNamespace

    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app_context))


async def test_a_config_edit_reaches_the_next_tool_call_without_reconnecting(
    temporary_database, monkeypatch, tmp_path
):
    from unittest.mock import AsyncMock

    import moonlighter.server as server
    from moonlighter.discovery.archive import ArchiveResult

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    _write(config_path, "score_threshold: 7.0\n")
    service = AsyncMock(return_value=ArchiveResult())
    monkeypatch.setattr(server.scan_service, "archive_stale_jobs", service)
    api_caller = object()
    monkeypatch.setattr(server, "make_caller", lambda config: api_caller)
    async with server.lifespan(server.mcp) as app_context:
        await server.archive_stale_jobs(context=_context_for(app_context))
        app_context.llm_caller = None
        _write(config_path, "score_threshold: 8.5\n", later_than=config_path)
        await server.archive_stale_jobs(context=_context_for(app_context))
    assert service.await_args_list[0].args[2]["score_threshold"] == 7.0
    assert service.await_args_list[1].args[2]["score_threshold"] == 8.5
    # The caller depends on llm_backend, so a config edit rebuilds it.
    assert app_context.llm_caller is api_caller


async def test_a_profile_edit_reaches_the_next_tool_call(temporary_database, monkeypatch, tmp_path):
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with server.lifespan(server.mcp) as app_context:
        assert server._app(_context_for(app_context)).profile["headline"] == "Before"
        _write(profile_path, "headline: After\n", later_than=profile_path)
        assert server._app(_context_for(app_context)).profile["headline"] == "After"


async def test_an_unchanged_config_is_not_read_again(temporary_database, monkeypatch, tmp_path):
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 7.0\n")
    async with server.lifespan(server.mcp) as app_context:
        config = app_context.config
        server._app(_context_for(app_context))
        assert app_context.config is config


async def test_an_invalid_config_edit_keeps_the_last_good_one_and_warns(
    temporary_database, monkeypatch, tmp_path, caplog
):
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    _write(config_path, "score_threshold: 7.0\n")
    async with server.lifespan(server.mcp) as app_context:
        _write(config_path, "scan_concurrency: five\n", later_than=config_path)
        app = server._app(_context_for(app_context))
    assert app.config["score_threshold"] == 7.0
    assert "config.yaml" in caplog.text


async def test_a_deleted_profile_becomes_empty(temporary_database, monkeypatch, tmp_path):
    """Unlike a deleted config, a deleted profile is a legitimate state: the server
    boots with {} when profile.yaml is absent, so a deletion mid-session means the same."""
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with server.lifespan(server.mcp) as app_context:
        profile_path.unlink()
        assert server._app(_context_for(app_context)).profile == {}


async def test_a_malformed_profile_edit_keeps_the_last_good_one_and_warns(
    temporary_database, monkeypatch, tmp_path, caplog
):
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    profile_path = tmp_path / "profile.yaml"
    _write(profile_path, "headline: Before\n")
    async with server.lifespan(server.mcp) as app_context:
        _write(profile_path, "headline: [unclosed\n", later_than=profile_path)
        app = server._app(_context_for(app_context))
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
async def test_an_edit_that_is_not_a_mapping_keeps_the_last_good_file(
    temporary_database, monkeypatch, tmp_path, caplog, file_name, bad_text
):
    """A list, a scalar, or an empty file (an editor that truncates, then writes)
    must not replace the settings: one tool call on defaults mid-write is the
    2026-09-25 class of bug."""
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 8.0\n")
    _write(tmp_path / "profile.yaml", "headline: Before\n")
    async with server.lifespan(server.mcp) as app_context:
        _write(tmp_path / file_name, bad_text, later_than=tmp_path / file_name)
        app = server._app(_context_for(app_context))
    assert app.config["score_threshold"] == 8.0
    assert app.profile == {"headline": "Before"}
    assert file_name in caplog.text


async def test_a_deleted_config_keeps_the_last_good_one(
    temporary_database, monkeypatch, tmp_path, caplog
):
    import moonlighter.server as server

    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    _write(tmp_path / "config.yaml", "score_threshold: 8.0\n")
    async with server.lifespan(server.mcp) as app_context:
        (tmp_path / "config.yaml").unlink()
        app = server._app(_context_for(app_context))
    assert app.config["score_threshold"] == 8.0
    assert "config.yaml" in caplog.text
