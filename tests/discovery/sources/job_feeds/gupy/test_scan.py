"""How the Gupy scanner maps portal postings and pages through the search."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.sources.job_feeds.gupy import GupyScanner

from tests.discovery.sources.job_feeds.gupy.fake_portal import GUPY_P1


def _make_gupy_client(url_map):
    """Like make_url_branching_client: branches the mock client's .get(url) on a
    substring match, raising loudly on an unexpected URL."""

    async def fake_get(url, headers=None):
        for substring, payload in url_map.items():
            if substring in url:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = payload
                return mock_response
        raise AssertionError(f"unexpected URL requested: {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_gupy_scan_maps_fields_and_strips_html():
    mock_client = _make_gupy_client({"offset=0": GUPY_P1})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="engenheiro")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "gupy"
    assert job.company == "acme"
    assert job.title == "Engenheiro de Software"
    assert job.url == "https://acme.gupy.io/job/tok?jobBoardSource=gupy_portal"
    assert job.remote_type == "remote"
    assert job.description == "Construir coisas"


async def test_gupy_missing_title_or_url_is_skipped():
    page = {
        "data": [
            {"id": 1, "jobUrl": "https://x.gupy.io/1"},  # missing name
            {"id": 2, "name": "Eng"},  # missing jobUrl
        ],
        "pagination": {"total": 2, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []


async def test_gupy_no_remote_work_uses_workplace_type():
    page = {
        "data": [
            {
                "id": 1,
                "name": "Eng",
                "jobUrl": "https://acme.gupy.io/1",
                "careerPageName": "acme",
                "isRemoteWork": False,
                "workplaceType": "hybrid",
            }
        ],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].remote_type == "hybrid"


async def test_gupy_missing_careerpagename_falls_back_to_gupy():
    page = {
        "data": [{"id": 1, "name": "Eng", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].company == "gupy"


async def test_gupy_no_description_yields_none():
    page = {
        "data": [{"id": 1, "name": "Eng", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 1, "limit": 10, "offset": 0},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs[0].description is None


async def test_gupy_paginates_across_pages():
    first_posting = {
        "data": [{"id": 1, "name": "Eng One", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 2, "limit": 1, "offset": 0},
    }
    second_posting = {
        "data": [{"id": 2, "name": "Eng Two", "jobUrl": "https://acme.gupy.io/2"}],
        "pagination": {"total": 2, "limit": 1, "offset": 1},
    }
    mock_client = _make_gupy_client({"offset=0": first_posting, "offset=1": second_posting})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert [scanned_job.title for scanned_job in jobs] == ["Eng One", "Eng Two"]
    assert mock_client.get.await_count == 2


async def test_gupy_zero_limit_field_does_not_spin():
    # The server reports "limit": 0 while still returning data and a total far
    # larger than what's been consumed. If the loop advanced offset by
    # data["pagination"]["limit"] it would add 0 and re-request the SAME offset
    # forever (bounded here only by the URL-branching mock raising on an
    # unexpected URL). Advancing by len(page) instead guarantees forward
    # progress every iteration.
    spinning_page = {
        "data": [{"id": 1, "name": "Spinner", "jobUrl": "https://acme.gupy.io/1"}],
        "pagination": {"total": 999999, "limit": 0, "offset": 0},
    }
    empty_page = {"data": [], "pagination": {"total": 999999, "limit": 0, "offset": 1}}
    mock_client = _make_gupy_client({"offset=0": spinning_page, "offset=1": empty_page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert len(jobs) == 1
    assert mock_client.get.await_count == 2


async def test_gupy_empty_page_terminates_immediately():
    page = {"data": [], "pagination": {"total": 0, "limit": 10, "offset": 0}}
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="eng")
    assert jobs == []
    assert mock_client.get.await_count == 1


async def test_gupy_default_keyword_when_not_provided():
    page = {"data": [], "pagination": {"total": 0, "limit": 10, "offset": 0}}
    mock_client = _make_gupy_client({"jobName=&limit=100&offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan()
    assert jobs == []


async def test_gupy_tags_only_description_yields_an_empty_string():
    page = {
        "data": [{"name": "Eng", "jobUrl": "https://acme.gupy.io/job/1", "description": "<p></p>"}],
        "pagination": {"total": 1},
    }
    mock_client = _make_gupy_client({"offset=0": page})
    with patch(
        "moonlighter.discovery.sources.job_feeds.gupy.httpx.AsyncClient", return_value=mock_client
    ):
        jobs = await GupyScanner().scan(keywords="engenheiro")
    assert jobs[0].description == ""
