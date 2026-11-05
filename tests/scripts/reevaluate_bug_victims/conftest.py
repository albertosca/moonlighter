"""Fixtures for the reevaluate_bug_victims pins: an initialised database and fakes for what main() builds itself."""

from unittest.mock import MagicMock

import pytest
import reevaluate_bug_victims
import reevaluation_batch
from moonlighter.core.db import init_db


@pytest.fixture
def caller_factory(monkeypatch, temporary_database):
    """Returns the fake make_caller; main() would otherwise build the real `claude -p` caller."""
    init_db()
    monkeypatch.setattr(reevaluate_bug_victims, "load_profile", lambda: {"name": "Ana"})
    # setup_logging() adds a process-wide file handler on ~/.moonlighter/app.log, once per process.
    monkeypatch.setattr(reevaluate_bug_victims, "setup_logging", lambda: None)
    factory = MagicMock(return_value="CALLER")
    monkeypatch.setattr(reevaluation_batch, "make_caller", factory)
    return factory
