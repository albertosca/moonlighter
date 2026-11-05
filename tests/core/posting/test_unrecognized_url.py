"""fetch_posting_via_ats returns None for a URL that matches no known ATS shape."""

import pytest
from moonlighter.core.posting import fetch_posting_via_ats


@pytest.mark.asyncio
async def test_unrecognized_url_returns_none():
    posting = await fetch_posting_via_ats("https://example.com/careers/dev")
    assert posting is None
