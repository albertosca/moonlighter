"""How the InHire scanner reads published jobs, their details, the tenant header and the job slug."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.discovery.sources.company_boards.inhire import InHireScanner, _inhire_slug

from tests.discovery.sources.fake_http_clients import make_mock_client

INHIRE_PAGE = {
    "tenantName": "Alice",
    "jobsPage": [
        {
            "jobId": "832b18f4-adf6-4c32-8e1b-18321e0b8069",
            "displayName": " Design l Creative Design ",
            "status": "published",
            "workplaceType": "Hybrid",
            "location": "São Paulo, SP, BR",
        },
        {
            "jobId": "aaaa",
            "displayName": "Backend Engineer",
            "status": "published",
            "workplaceType": "Remote",
            "location": "BR",
        },
        {
            "jobId": "bbbb",
            "displayName": "Old Role",
            "status": "draft",
            "workplaceType": "On-site",
            "location": "SP",
        },
    ],
}


INHIRE_DETAIL = {
    "832b18f4-adf6-4c32-8e1b-18321e0b8069": {
        "displayName": "Design l Creative Design",
        "description": "<p>Craft <b>visual</b> systems.</p>",
    },
    "aaaa": {
        "displayName": "Backend Engineer",
        "description": "<div>Build APIs<br>in Python.</div>",
    },
}


def _make_inhire_client(page=INHIRE_PAGE, details=INHIRE_DETAIL, detail_status=200):
    """Mock client that serves the listing at BASE and per-job details at
    BASE/{jobId} — the two-endpoint shape the real API has.
    """
    mock_client = MagicMock()

    async def get(url, headers=None):
        http_response = MagicMock()
        job_id = url.rsplit("/", 1)[-1]
        if url.endswith("/job-posts/public/pages"):
            http_response.status_code = 200
            http_response.json.return_value = page
        elif job_id in details and detail_status == 200:
            http_response.status_code = 200
            http_response.json.return_value = details[job_id]
        else:
            http_response.status_code = detail_status
        return http_response

    mock_client.get = AsyncMock(side_effect=get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


async def test_inhire_scan_parses_published_jobs_only():
    mock_client = _make_inhire_client()
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await InHireScanner().scan(["alice"])

    assert [scanned_job.title for scanned_job in jobs] == [
        "Design l Creative Design",
        "Backend Engineer",
    ]
    assert jobs[0].source == "inhire"
    assert jobs[0].company == "alice"
    # Slug derived from displayName: without it the SPA renders a black screen
    # (verified live 2026-08-21, both jobs, incognito included).
    assert jobs[0].url == (
        "https://alice.inhire.app/vagas/832b18f4-adf6-4c32-8e1b-18321e0b8069"
        "/design-l-creative-design"
    )
    assert jobs[0].remote_type == "hybrid"
    assert jobs[1].remote_type == "remote"
    # Description now comes from the public detail endpoint (re-verified live
    # 2026-08-24: HTTP 200, no auth — the old "403" docstring was stale),
    # HTML stripped like _fetch_description does.
    assert jobs[0].description == "Craft visual systems."
    assert jobs[1].description == "Build APIs in Python."


async def test_inhire_detail_failure_keeps_the_listing_job():
    # One broken detail must not cost the posting — it degrades to the old
    # behavior (description None → needs_review), never drops the job.
    mock_client = _make_inhire_client(detail_status=500)
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await InHireScanner().scan(["alice"])
    assert [scanned_job.description for scanned_job in jobs] == [None, None]
    assert len(jobs) == 2


async def test_inhire_detail_wrong_shape_degrades_to_no_description():
    # Valid JSON that isn't an object (the API answering with a list) must
    # degrade exactly like an HTTP failure: keep the job, description None.
    details = {"832b18f4-adf6-4c32-8e1b-18321e0b8069": ["not", "a", "dict"], "aaaa": ["nope"]}
    mock_client = _make_inhire_client(details=details)
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await InHireScanner().scan(["alice"])
    assert [scanned_job.description for scanned_job in jobs] == [None, None]


def test_inhire_slug_reproduces_the_measured_pipe_case():
    # The one canonical example measured live (2026-08-21):
    # "Senior Elixir Engineer | Plataform" → senior-elixir-engineer-or-plataform
    assert (
        _inhire_slug("Senior Elixir Engineer | Plataform") == "senior-elixir-engineer-or-plataform"
    )
    assert _inhire_slug("Analista Sênior de Facilities & Compras") == (
        "analista-senior-de-facilities-compras"
    )


async def test_inhire_sends_the_tenant_header():
    mock_client = make_mock_client(INHIRE_PAGE)
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        await InHireScanner().scan(["alice"])
    first = mock_client.get.call_args_list[0]
    assert first.kwargs["headers"]["X-Tenant"] == "alice"
    assert first.args[0] == "https://api.inhire.app/job-posts/public/pages"
    # Every detail call carries the tenant header too — the API 403s without it.
    for call in mock_client.get.call_args_list[1:]:
        assert call.kwargs["headers"]["X-Tenant"] == "alice"


async def test_inhire_wrong_shape_counts_as_error():
    mock_client = make_mock_client(["not", "a", "dict"])
    stats = {}
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await InHireScanner().scan(["alice"], stats=stats)
    assert jobs == []
    assert stats["inhire"].errors == 1


async def test_inhire_non_list_jobs_page_counts_as_error():
    mock_client = make_mock_client({"tenantName": "Alice", "jobsPage": "oops"})
    stats = {}
    with patch(
        "moonlighter.discovery.sources.company_boards.inhire.httpx.AsyncClient",
        return_value=mock_client,
    ):
        jobs = await InHireScanner().scan(["alice"], stats=stats)
    assert jobs == []
    assert stats["inhire"].errors == 1
