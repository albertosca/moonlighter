"""A failed fetch is not "zero open jobs".

Found live on 2026-09-16: a Greenhouse fetch answered HTTP 404 and the run archived a
status='new', score-8.5 job with failed_companies == []. The real HTTP scanners never raise —
gather_jobs swallows a failed slug, counts it in stats[source].errors and returns [] — so the
exception guard in test_listing_check protects a path production does not take.
"""

from unittest.mock import patch

from moonlighter.discovery.sources.base import SourceStats
from moonlighter.discovery.sources.company_boards.greenhouse import GreenhouseScanner
from moonlighter.discovery.staleness import find_stale_jobs

from tests.discovery.sources.fake_http_clients import make_simple_client
from tests.discovery.staleness.fake_jobs import CONFIG, make_job


class _FetchFailingScanner:
    """Shaped like every gather_jobs-backed scanner: [] back, the failure only in the stats."""

    async def scan(self, company_slugs, **keyword_arguments):
        stats = keyword_arguments.get("stats")
        if stats is not None:
            stats["greenhouse"] = SourceStats(companies=len(company_slugs), jobs=0, errors=1)
        return []


async def test_fetch_error_reported_through_stats_marks_company_failed_not_stale():
    job = make_job(url="https://x.com/1")
    result = await find_stale_jobs(
        {("greenhouse", "acme"): [job]}, {"greenhouse": _FetchFailingScanner()}, CONFIG
    )
    assert result.stale == []
    assert result.failed_companies == ["acme"]


async def test_http_404_on_the_real_greenhouse_scanner_marks_company_failed_not_stale():
    # The exact live scenario, through the real scanner and the real
    # gather_jobs: only the HTTP client is faked, and it answers 404.
    job = make_job(url="https://boards.greenhouse.io/acme/jobs/1")
    with patch(
        "moonlighter.discovery.sources.company_boards.gathering.httpx.AsyncClient",
        return_value=make_simple_client({}, status=404),
    ):
        result = await find_stale_jobs(
            {("greenhouse", "acme"): [job]}, {"greenhouse": GreenhouseScanner()}, CONFIG
        )
    assert result.stale == []
    assert result.failed_companies == ["acme"]
