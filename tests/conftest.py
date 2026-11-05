"""Session-wide pytest setup: the e2e guard, the isolated home and the shared fixtures."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from moonlighter.core.config import api_key
from tests import _e2e_guard

_SNAPSHOTS = Path(__file__).parent / "snapshots"

_SESSION_HOME = pytest.StashKey[str]()


def pytest_configure(config: pytest.Config) -> None:
    _register_e2e_guard(config)
    _isolate_moonlighter_home(config)


def _register_e2e_guard(config: pytest.Config) -> None:
    """Turn a skipped e2e test into a failure (see tests/_e2e_guard.py).

    Registered here rather than through ``-p`` in addopts: ``-p`` imports the
    plugin before the rootdir is on sys.path, so ``tests._e2e_guard`` would not
    resolve.
    """
    if not config.pluginmanager.is_registered(_e2e_guard):
        config.pluginmanager.register(_e2e_guard, "tests._e2e_guard")


def _isolate_moonlighter_home(config: pytest.Config) -> None:
    """Point MOONLIGHTER_HOME at a session temp directory before any test module is imported.

    A fixture runs only after the test modules are imported, and moonlighter_home()
    falls back to the real ~/.moonlighter when the variable is unset, so anything
    that reads it at import or collection time would reach real user data.
    pytest_configure runs before collection and is the standard hook for
    environment setup that must precede it.

    MOONLIGHTER_DB_PATH is removed for the same reason: moonlighter.core.db.db_path()
    prefers it over moonlighter_home() / "moonlighter.db", so a developer shell that
    exports it would send init_db() to that developer's own database. The per-test
    temporary_database fixture below still sets it through monkeypatch, which takes
    precedence because it runs later.

    One write escapes: moonlighter.core.log hardcodes ~/.moonlighter/app.log
    (_DEFAULT_LOG_PATH) whatever MOONLIGHTER_HOME says, so importing a module that
    calls get_logger appends to the developer's real log.
    """
    session_home = tempfile.mkdtemp(prefix="moonlighter-test-home-")
    config.stash[_SESSION_HOME] = session_home
    os.environ["MOONLIGHTER_HOME"] = session_home
    os.environ.pop("MOONLIGHTER_DB_PATH", None)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the session temp directory, best-effort: it lives under the OS temp directory anyway."""
    session_home = config.stash.get(_SESSION_HOME, None)
    if session_home is not None:
        shutil.rmtree(session_home, ignore_errors=True)
        del config.stash[_SESSION_HOME]


@pytest.fixture
def temporary_database(monkeypatch, tmp_path):
    """Point MOONLIGHTER_DB_PATH at a fresh temp file for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("MOONLIGHTER_DB_PATH", db_path)
    return db_path


@pytest.fixture
def snapshot_text(request):
    def _check(actual: str, name: str) -> None:
        path = _SNAPSHOTS / f"{request.node.module.__name__.split('.')[-1]}.{name}.txt"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual)
            pytest.fail(f"snapshot written: {path} — inspect it, then re-run")
        assert actual == path.read_text()

    return _check


@pytest.fixture(autouse=True)
def _no_real_api_env_file(tmp_path_factory, monkeypatch):
    # load_config fills ANTHROPIC_API_KEY from ~/.config/anthropic/api.env on the
    # api backend; without this, any test loading an api config would read the
    # developer's real key into the test process.
    missing_file = tmp_path_factory.mktemp("no-api-env") / "api.env"
    monkeypatch.setattr(api_key, "anthropic_api_env_file", lambda: missing_file)
