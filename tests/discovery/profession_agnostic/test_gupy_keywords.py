"""Gupy is searched only with the keywords the profile gives, never a default (#120)."""

from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.discovery.scan.collection import collect_raw_jobs


async def _collect(keywords, config):
    with (
        patch("moonlighter.discovery.scan.collection.build_http_scanners", return_value={}),
        patch("moonlighter.discovery.scan.collection.discover_entry_points", return_value=[]),
    ):
        return await collect_raw_jobs(keywords, config, {})


@pytest.mark.parametrize("keywords", ["", "   "])
async def test_gupy_without_keywords_is_skipped_with_a_warning_not_searched_as_software(keywords):
    with patch("moonlighter.discovery.scan.portals.GupyScanner") as mock_gupy:
        mock_gupy.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, warning = await _collect(keywords, {"scan_gupy": True})
    mock_gupy.return_value.scan.assert_not_called()
    assert raw_jobs == []
    assert warning is not None
    assert "scan_gupy" in warning
    assert "software" not in warning.lower()


async def test_gupy_off_and_no_keywords_says_nothing():
    _, warning = await _collect("", {})
    assert warning is None


async def test_gupy_with_keywords_searches_exactly_them():
    with patch("moonlighter.discovery.scan.portals.GupyScanner") as mock_gupy:
        mock_gupy.return_value.scan = AsyncMock(return_value=[])
        await _collect("enfermeiro", {"scan_gupy": True})
    assert mock_gupy.return_value.scan.await_args.kwargs["keywords"] == "enfermeiro"
