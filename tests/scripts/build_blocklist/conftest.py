"""Fixtures for the build_blocklist pins: a temporary home and database, and logging that stays off the developer's files."""

import build_blocklist
import pytest

from moonlighter.core.db import init_db


@pytest.fixture
def home(monkeypatch, tmp_path, temporary_database):
    """The MOONLIGHTER_HOME main() writes blocklist_learned.yaml under, with an initialised database."""
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    init_db()
    # setup_logging() adds a process-wide file handler on ~/.moonlighter/app.log, once per process.
    monkeypatch.setattr(build_blocklist, "setup_logging", lambda: None)
    return tmp_path
