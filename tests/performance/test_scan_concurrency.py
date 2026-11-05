"""Scanning many companies at once is faster than scanning them one by one."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.sources.base import SourceStats
from moonlighter.discovery.sources.company_boards.ashby import AshbyScanner
from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from moonlighter.discovery.sources.company_boards.lever import LeverScanner
from tests.performance.timing import CONCURRENCY_RATIO

DELAY_SECONDS = 0.02


def _slow_client(payload):
    """Async-context client whose GET answers `payload` after DELAY_SECONDS."""

    async def slow_get(url, **keyword_arguments):
        await asyncio.sleep(DELAY_SECONDS)
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        return response

    client = MagicMock()
    client.get = slow_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def _assert_scan_is_concurrent(scanner, source, payload, *, company_count):
    """Scan `company_count` slugs at once, then one by one, and compare."""
    slugs = [f"company-{index}" for index in range(company_count)]
    client = _slow_client(payload)
    stats = {}

    with patch(
        "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
        return_value=client,
    ):
        start_time = time.perf_counter()
        await scanner.scan(slugs, stats=stats)
        concurrent_elapsed = time.perf_counter() - start_time

        start_time = time.perf_counter()
        for slug in slugs:
            await scanner.scan([slug])
        sequential_elapsed = time.perf_counter() - start_time

    # Zero errors is what proves the mocked fetch really ran: a mock the scanner
    # never calls makes every company fail, quickly, and the timing still "passes".
    assert stats[source] == SourceStats(companies=company_count, jobs=0, errors=0)
    assert concurrent_elapsed < sequential_elapsed * CONCURRENCY_RATIO, (
        f"{source}: concurrent {concurrent_elapsed:.3f}s should be under "
        f"{CONCURRENCY_RATIO:.0%} of sequential {sequential_elapsed:.3f}s"
    )


async def test_greenhouse_scan_20_companies_concurrent():
    await _assert_scan_is_concurrent(
        GreenhouseScanner(), "greenhouse", {"jobs": []}, company_count=20
    )


async def test_lever_scan_15_companies_concurrent():
    await _assert_scan_is_concurrent(LeverScanner(), "lever", [], company_count=15)


async def test_ashby_scan_10_companies_concurrent():
    """Ashby is fetched with GET (the REST posting API), not the retired GraphQL POST."""
    await _assert_scan_is_concurrent(AshbyScanner(), "ashby", {"jobs": []}, company_count=10)
