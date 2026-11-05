"""Portal feeds are filtered by title keywords before any evaluation."""

from unittest.mock import AsyncMock, patch

from moonlighter.discovery.portals import _matches_keywords, _scan_remoteok
from moonlighter.discovery.sources.base import RawJob


def test_matches_keywords_any_term_case_insensitive():
    assert _matches_keywords("Senior Backend Engineer", "backend, sre")
    assert not _matches_keywords("Account Executive", "backend, sre")
    assert _matches_keywords("Anything", "")  # no keywords = no filter


async def test_portal_feed_is_filtered_by_keywords():
    jobs = [
        RawJob(source="remoteok", company="a", title="Backend Engineer", url="https://r.ok/1"),
        RawJob(source="remoteok", company="b", title="Marketing Lead", url="https://r.ok/2"),
    ]
    with patch(
        "moonlighter.discovery.portals.RemoteOKScanner.scan",
        new=AsyncMock(return_value=jobs),
    ):
        got = await _scan_remoteok({"scan_remoteok": True}, {}, "backend")
    assert [job.title for job in got] == ["Backend Engineer"]
