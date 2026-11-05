"""What find_stale_jobs logs when a check cannot answer: text, level and traceback."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.sources.base import SourceStats
from moonlighter.discovery.staleness import find_stale_jobs

from tests.discovery.staleness.fake_jobs import CHECKERS, CONFIG, make_job, make_scanner

LOGGER = "moonlighter.discovery.staleness"


def _staleness_records(caplog):
    return [record for record in caplog.records if record.name == LOGGER]


async def test_a_scanner_exception_is_logged_as_a_warning_with_its_traceback(caplog):
    scanner = MagicMock()
    scanner.scan = AsyncMock(side_effect=RuntimeError("timeout"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await find_stale_jobs(
            {("greenhouse", "acme"): [make_job()]}, {"greenhouse": scanner}, CONFIG
        )
    (record,) = _staleness_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "staleness: greenhouse scan failed for acme — timeout"
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


async def test_a_listing_that_is_not_a_list_is_logged_without_a_traceback(caplog):
    scanners = {"greenhouse": make_scanner("not a list")}
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await find_stale_jobs({("greenhouse", "acme"): [make_job()]}, scanners, CONFIG)
    (record,) = _staleness_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "staleness: greenhouse scan returned unexpected type for acme"
    assert record.exc_info is None


async def test_a_fetch_error_in_the_stats_is_logged_with_its_count_and_no_traceback(caplog):
    class FetchFailingScanner:
        async def scan(self, company_slugs, **keyword_arguments):
            keyword_arguments["stats"]["greenhouse"] = SourceStats(companies=1, jobs=0, errors=2)
            return []

    scanners = {"greenhouse": FetchFailingScanner()}
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await find_stale_jobs({("greenhouse", "acme"): [make_job()]}, scanners, CONFIG)
    (record,) = _staleness_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == (
        "staleness: greenhouse fetch failed for acme (2 error(s)) — not treated as closed"
    )
    assert record.exc_info is None


async def test_a_checker_plugin_exception_is_logged_as_a_warning_with_its_traceback(caplog):
    job = make_job(source="acme_ats", company="acme")
    checker = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch(CHECKERS, return_value={"acme_ats": checker}),
        caplog.at_level(logging.DEBUG, logger=LOGGER),
    ):
        await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    (record,) = _staleness_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "staleness: acme_ats checker failed for acme — boom"
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
