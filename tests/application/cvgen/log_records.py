"""Reading the log records a test captured."""

import logging

import pytest


def logged_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The message of every WARNING record `caplog` captured, in order."""
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
