import os
import shutil
import tempfile

import pytest

_session_home: str | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Point GAUNTLER_HOME at a session-scoped temp dir BEFORE pytest imports
    any test module.

    gauntler.server calls harden_permissions() and init_db() at *module import
    time*, and gauntler_home() defaults to the real ~/.gauntler when
    GAUNTLER_HOME is unset. Test modules get imported during collection, which
    happens before ordinary (even session-scoped) fixtures run — so a fixture
    is too late to prevent that first import from touching real user data.
    pytest_configure runs before collection/import and is the standard hook
    for environment setup that must precede it.

    Only GAUNTLER_HOME is set here: gauntler.core.db._db_path() already falls
    back to gauntler_home() / "gauntler.db" when GAUNTLER_DB_PATH is unset, so
    this alone keeps init_db() out of the real directory too. The per-test
    tmp_db fixture below still overrides GAUNTLER_DB_PATH with a fresh path
    per test via monkeypatch, which takes precedence over this session-wide
    default since it's set later and per-test.
    """
    global _session_home
    _session_home = tempfile.mkdtemp(prefix="gauntler-test-home-")
    os.environ["GAUNTLER_HOME"] = _session_home


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
    monkeypatch.setenv("GAUNTLER_DB_PATH", db_path)
    return db_path
