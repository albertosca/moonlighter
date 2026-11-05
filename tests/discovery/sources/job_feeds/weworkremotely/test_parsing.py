"""How a We Work Remotely RSS item becomes a job: company, title, date, description and the request it sends."""

from unittest.mock import patch

from moonlighter.core.http_fetch import HEADERS
from moonlighter.discovery.sources.job_feeds.weworkremotely import WeWorkRemotelyScanner

from tests.discovery.sources.job_feeds.weworkremotely.fake_feed import WWR_RSS, make_rss_client


async def test_wwr_scan_splits_company_from_title_and_strips_html():
    mock_client = make_rss_client(WWR_RSS)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()

    assert len(jobs) == 2  # third item has no <link>, skipped
    job = jobs[0]
    assert job.source == "weworkremotely"
    assert job.company == "Acme"
    assert job.title == "Senior Backend Engineer"
    assert job.url == "https://weworkremotely.com/remote-jobs/acme-senior-backend-engineer"
    assert job.location == "Anywhere in the World"
    assert job.remote_type == "remote"
    assert job.description == "Build things."
    assert job.posted_at is not None
    assert job.posted_at.year == 2026
    assert job.posted_at.month == 6
    assert job.posted_at.day == 30


async def test_wwr_title_without_colon_falls_back_to_source_name_company():
    mock_client = make_rss_client(WWR_RSS)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    no_colon_job = next(
        scanned_job for scanned_job in jobs if scanned_job.title == "Frontend Developer Wanted"
    )
    assert no_colon_job.company == "WeWorkRemotely"


async def test_wwr_missing_pubdate_leaves_posted_at_none():
    rss = WWR_RSS.replace("<pubDate>Tue, 30 Jun 2026 20:32:52 +0000</pubDate>", "", 1)
    mock_client = make_rss_client(rss)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs[0].posted_at is None


async def test_wwr_missing_description_yields_none():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Acme: No Description Role</title>
      <region>Worldwide</region>
      <link>https://weworkremotely.com/remote-jobs/acme-no-description-role</link>
    </item>
  </channel>
</rss>"""
    mock_client = make_rss_client(rss)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs[0].description is None


async def test_wwr_tags_only_description_yields_none():
    rss = WWR_RSS.replace(
        "&lt;p&gt;Build &lt;strong&gt;things&lt;/strong&gt;.&lt;/p&gt;", "&lt;p&gt;&lt;/p&gt;", 1
    )
    mock_client = make_rss_client(rss)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await WeWorkRemotelyScanner().scan()
    assert jobs[0].title == "Senior Backend Engineer"
    assert jobs[0].description is None


async def test_wwr_sends_the_moonlighter_user_agent():
    mock_client = make_rss_client(WWR_RSS)
    with patch(
        "moonlighter.discovery.sources.job_feeds.weworkremotely.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await WeWorkRemotelyScanner().scan()
    mock_client.get.assert_awaited_once_with(
        "https://weworkremotely.com/remote-jobs.rss", headers=HEADERS
    )
