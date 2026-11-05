"""Fake stored jobs and listing scanners for the staleness tests."""

from unittest.mock import AsyncMock, MagicMock

CONFIG: dict = {}
CHECKERS = "moonlighter.discovery.staleness.discover_entry_points_by_name"


def make_job(
    job_id=1,
    *,
    source="greenhouse",
    company="acme",
    url="https://x.com/1",
    title="Eng",
):
    job = MagicMock()
    job.id = job_id
    job.source = source
    job.company = company
    job.url = url
    job.title = title
    return job


def make_scanner(return_value):
    scanner = MagicMock()
    scanner.scan = AsyncMock(return_value=return_value)
    return scanner
