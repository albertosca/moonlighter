"""The frozen answer-bank clock the exact-date pins share."""

from types import SimpleNamespace

import pytest
from moonlighter.application.answers.bank import store

from tests.application.answers.bank.store.bank_rows import FROZEN_NOW


@pytest.fixture
def frozen_clock(monkeypatch):
    """Answer-bank time stands still at FROZEN_NOW, so a boundary can be exact."""
    monkeypatch.setattr(store, "datetime", SimpleNamespace(now=lambda: FROZEN_NOW))
