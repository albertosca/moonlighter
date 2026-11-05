"""ScanLog keeps one row per job URL whatever the source, and stamps scanned_at at creation."""

import os
from datetime import datetime, timedelta

import pytest
from moonlighter.core.db import ScanLog, init_db
from peewee import IntegrityError


def test_scan_log_dedup(temporary_database):
    os.environ["MOONLIGHTER_DB_PATH"] = temporary_database
    init_db()
    ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")
    urls = {row.job_url for row in ScanLog.select()}
    assert "https://example.com/job/1" in urls
    # Second insert with same URL should raise IntegrityError
    with pytest.raises(IntegrityError):
        ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")


def test_scanlog_same_url_different_source_raises(temporary_database):
    """ScanLog.job_url is UNIQUE regardless of source — same URL with different source raises."""
    init_db()
    ScanLog.create(job_url="https://example.com/job/dup-src", source="greenhouse")
    with pytest.raises(IntegrityError):
        ScanLog.create(job_url="https://example.com/job/dup-src", source="lever")


# --- ScanLog: timestamp ---


def test_scanlog_scanned_at_is_recent(temporary_database):
    init_db()
    before = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    log = ScanLog.create(job_url="https://example.com/job/ts", source="greenhouse")
    after = datetime.now()  # noqa: DTZ005 - the database stores naive local time
    assert before - timedelta(seconds=5) <= log.scanned_at <= after + timedelta(seconds=5)
