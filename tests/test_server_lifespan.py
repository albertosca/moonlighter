"""The server's lifespan: what it yields, when it refuses to boot, and that importing the server does nothing."""

import threading

import pytest

from moonlighter.app_context import AppContext
from moonlighter.core import db as database
from moonlighter.core import log
from moonlighter.core.config import loading, permissions
from moonlighter.core.config.errors import ConfigError
from moonlighter.server import lifespan, mcp
from tests._fresh_import import import_server_afresh


async def test_lifespan_yields_populated_appcontext(temporary_database):
    async with lifespan(mcp) as app_context:
        assert isinstance(app_context, AppContext)
        assert isinstance(app_context.config, dict)
        assert app_context.llm_caller is not None
        assert isinstance(app_context.startup_warnings, list)


async def test_lifespan_rejects_invalid_config(temporary_database, monkeypatch):
    # Raises the way the real loader does: validation now runs inside loading.
    monkeypatch.setattr(
        "moonlighter.server.load_config", lambda: loading.build_config({"scan_concurrency": "five"})
    )
    with pytest.raises(ConfigError):
        async with lifespan(mcp):
            pass  # must raise before yielding


async def test_lifespan_prints_permission_warnings(temporary_database, monkeypatch, capsys):
    monkeypatch.setattr(
        "moonlighter.server.harden_permissions", lambda: ["could not chmod ~/.moonlighter"]
    )
    async with lifespan(mcp) as app_context:
        assert app_context.permission_warnings == ["could not chmod ~/.moonlighter"]
    assert "could not chmod ~/.moonlighter" in capsys.readouterr().err


def test_importing_server_has_no_side_effects(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        loading,
        "load_config",
        lambda *positional_arguments, **keyword_arguments: calls.append("load_config") or {},
    )
    monkeypatch.setattr(
        database,
        "init_db",
        lambda *positional_arguments, **keyword_arguments: calls.append("init_db"),
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
    import_server_afresh(monkeypatch)
    assert calls == []  # importing the server must not load config / init db / harden perms


async def test_the_startup_checks_run_off_the_event_loop(temporary_database, monkeypatch):
    """`opencode models` can take up to 20 s: the boot checks must not stall the loop."""
    threads: list[str] = []

    def record_thread(config, profile):
        threads.append(threading.current_thread().name)
        return []

    monkeypatch.setattr("moonlighter.server.validate_startup", record_thread)
    async with lifespan(mcp):
        pass
    assert threads
    assert threads[0] != threading.main_thread().name
