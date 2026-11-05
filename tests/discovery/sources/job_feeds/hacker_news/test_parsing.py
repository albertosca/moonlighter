"""How a 'Who is hiring?' comment becomes a job: company, title, remote type and location."""

from unittest.mock import patch

import pytest

from moonlighter.discovery.sources.job_feeds.hacker_news import HNWhoIsHiringScanner
from tests.discovery.sources.job_feeds.hacker_news.fake_api import (
    HN_BASE,
    hn_url_map,
    make_hn_client,
)


async def test_hn_scan_finds_thread_and_parses_pipe_separated_title():
    mock_client = make_hn_client(hn_url_map())
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()

    acme = next(scanned_job for scanned_job in jobs if scanned_job.company == "Acme")
    assert acme.source == "hn_whoishiring"
    assert acme.title == "Remote | Full-time Build things."
    assert acme.url == "https://news.ycombinator.com/item?id=201"
    assert acme.remote_type == "remote"  # the header says so
    assert acme.location == "Remote"


async def test_hn_parse_title_truncates_long_rest_after_separator():
    """Live-discovered (2026-07-21): HN comments render paragraphs as <p>,
    which the tag-strip turns into a space, not a newline -- so 'first line'
    is really 'the whole flattened comment' and an unbounded `rest` after
    the first separator became the entire ~1200-char posting. Cap it like
    the no-separator fallback already caps full_text.
    """
    long_rest = "Senior Engineer, Genomics Infrastructure | Memphis, TN | ONSITE or REMOTE | " + (
        "x" * 200
    )
    text = f"Acme | {long_rest}"
    url_map = hn_url_map(kids=(201,))
    url_map[f"{HN_BASE}/item/201.json"] = {"id": 201, "text": text}
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    job = next(scanned_job for scanned_job in jobs if scanned_job.company == "Acme")
    assert len(job.title) <= 81  # 80 chars + the "…" ellipsis
    assert job.title.endswith("…")


async def test_hn_scan_falls_back_to_prose_when_no_separator():
    mock_client = make_hn_client(hn_url_map())
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()

    fallback = next(scanned_job for scanned_job in jobs if scanned_job.url.endswith("id=202"))
    assert fallback.company == "HN Who's Hiring"
    assert "No separator in this first line" in fallback.title


async def test_hn_parse_title_falls_through_when_separator_leads_with_empty_company():
    """A first line starting with the '|' separator strips to an empty
    company on that attempt -- must fall through (not return an empty
    company) to try '-' next and, since this fixture has no '-' either,
    all the way to the final prose fallback.
    """
    text = "| Remote position available now for engineers"
    url_map = hn_url_map(kids=(201,))
    url_map[f"{HN_BASE}/item/201.json"] = {"id": 201, "text": text}
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    assert len(jobs) == 1
    assert jobs[0].company == "HN Who's Hiring"
    assert jobs[0].title == text


async def _hn_job(text):
    url_map = hn_url_map(kids=(201,))
    url_map[f"{HN_BASE}/item/201.json"] = {"id": 201, "text": text}
    mock_client = make_hn_client(url_map)
    with patch(
        "moonlighter.discovery.sources.job_feeds.hacker_news.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await HNWhoIsHiringScanner().scan()
    return jobs[0]


@pytest.mark.parametrize(
    ("header", "remote_type", "location"),
    [
        ("Acme | Backend Engineer | Memphis, TN | ONSITE | Full-time", "onsite", None),
        ("Acme | Backend Engineer | REMOTE | Full-time", "remote", "REMOTE"),
        (
            "Acme | Backend Engineer | Remote (Worldwide) | Full-time",
            "remote",
            "Remote (Worldwide)",
        ),
        ("Acme | Backend Engineer | Berlin | HYBRID", "hybrid", None),
        ("Acme | Backend Engineer | Austin | In-Office", "onsite", None),
        # Ambiguous or silent headers stay unknown, never guessed.
        ("Acme | Backend Engineer | Varies between REMOTE and HYBRID", None, None),
        ("Acme | Backend Engineer | ONSITE or REMOTE", None, None),
        ("Acme | Backend Engineer | ONSITE | Remote (US)", None, None),
        ("Acme | Backend Engineer | Austin | Full-time", None, None),
        ("Acme - Backend Engineer in Austin", None, None),
    ],
)
async def test_hn_header_segments_fill_remote_type_and_location(header, remote_type, location):
    job = await _hn_job(header)
    assert job.remote_type == remote_type
    assert job.location == location


async def test_hn_remote_word_in_the_body_does_not_set_remote_type():
    """Only the pipe-separated header counts: 'remote' in the prose of the JD is
    not a statement about this posting's workplace.
    """
    body = "Acme | Backend Engineer | Austin " + ("blah " * 80) + "| we are not remote-friendly"
    job = await _hn_job(body)
    assert job.remote_type is None
