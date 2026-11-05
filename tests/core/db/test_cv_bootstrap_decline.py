"""cv_bootstrap_declined stays False until a decline is recorded, and recording a second decline is harmless."""

from moonlighter.core.cv_bootstrap import cv_bootstrap_declined, record_cv_bootstrap_decline
from moonlighter.core.db import init_db


def test_cv_bootstrap_declined_is_false_until_recorded(temporary_database):
    init_db()
    assert cv_bootstrap_declined() is False
    record_cv_bootstrap_decline()
    assert cv_bootstrap_declined() is True


def test_record_cv_bootstrap_decline_is_idempotent(temporary_database):
    init_db()
    record_cv_bootstrap_decline()
    record_cv_bootstrap_decline()  # must not raise (e.g. a second decline check)
    assert cv_bootstrap_declined() is True
