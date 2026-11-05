"""fetch_description keeps only a page's text, dropping script and style contents and truncating at an unclosed one, and reports a non-200 as an error instead of a description."""

from unittest.mock import AsyncMock, MagicMock, patch

from moonlighter.core.posting import fetch_description


async def test_fetch_description_drops_style_and_script_contents():
    html_page = "<style>.a{color:red}</style><script>var x=1;</script><p>Real text</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", client_class):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real text"
    assert "color" not in description
    assert "var x" not in description


async def test_fetch_description_truncates_at_an_unclosed_style_tag():
    # job #2646 (Ziflow): a bare tag-strip left a whole CSS bundle as the
    # "description". The paired-tag regex fixed the well-formed case, but a
    # malformed page with NO matching </style> anywhere lets the regex's
    # non-greedy .*?</\1> simply fail to match — the tag and everything after
    # it survive untouched. Measured by direct execution before this fix.
    html_page = "<div>Real desc before</div><style>.a{color:red}<p>unreliable tail</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", client_class):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real desc before"
    assert "color" not in description


async def test_fetch_description_truncates_at_an_unclosed_script_tag():
    html_page = "<div>Real desc</div><script>var x = 1;<p>tail</p>"
    response = MagicMock(status_code=200, text=html_page)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", client_class):
        description, error = await fetch_description("https://example.com/job")
    assert error is None
    assert description == "Real desc"


async def test_fetch_description_reports_a_non_200_instead_of_guessing():
    client = MagicMock()
    client.get = AsyncMock(return_value=MagicMock(status_code=404, text=""))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.core.posting.httpx.AsyncClient", return_value=client):
        text, error = await fetch_description("https://x.com/job")
    assert text is None
    assert "HTTP 404" in (error or "")
