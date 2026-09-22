import os
import shutil
import tempfile
from pathlib import Path

import pytest

_SNAPSHOTS = Path(__file__).parent / "snapshots"

_session_home: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    _register_e2e_guard(config)
    _isolate_moonlighter_home()


def _register_e2e_guard(config: pytest.Config) -> None:
    """Turn a skipped e2e test into a failure (see tests/_e2e_guard.py).

    Registered here rather than through ``-p`` in addopts: ``-p`` imports the
    plugin before the rootdir is on sys.path, so ``tests._e2e_guard`` would not
    resolve.
    """
    from tests import _e2e_guard

    if not config.pluginmanager.is_registered(_e2e_guard):
        config.pluginmanager.register(_e2e_guard, "tests._e2e_guard")


def _isolate_moonlighter_home() -> None:
    """Point MOONLIGHTER_HOME at a session-scoped temp dir BEFORE pytest imports
    any test module.

    moonlighter.server calls harden_permissions() and init_db() at *module import
    time*, and moonlighter_home() defaults to the real ~/.moonlighter when
    MOONLIGHTER_HOME is unset. Test modules get imported during collection, which
    happens before ordinary (even session-scoped) fixtures run — so a fixture
    is too late to prevent that first import from touching real user data.
    pytest_configure runs before collection/import and is the standard hook
    for environment setup that must precede it.

    Only MOONLIGHTER_HOME is set here: moonlighter.core.db._db_path() already falls
    back to moonlighter_home() / "moonlighter.db" when MOONLIGHTER_DB_PATH is unset, so
    this alone keeps init_db() out of the real directory too. The per-test
    tmp_db fixture below still overrides MOONLIGHTER_DB_PATH with a fresh path
    per test via monkeypatch, which takes precedence over this session-wide
    default since it's set later and per-test.
    """
    global _session_home
    _session_home = tempfile.mkdtemp(prefix="moonlighter-test-home-")
    os.environ["MOONLIGHTER_HOME"] = _session_home


def pytest_unconfigure(config: pytest.Config) -> None:
    """Best-effort cleanup of the session temp dir; not strictly required
    since it lives under the OS temp dir, but tidy."""
    global _session_home
    if _session_home is not None:
        shutil.rmtree(_session_home, ignore_errors=True)
        _session_home = None


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Replace DB_PATH with a temp file for each test."""
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
