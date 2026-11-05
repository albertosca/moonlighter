"""Each portal feed is scanned only when its config flag is on."""

from unittest.mock import ANY, AsyncMock, patch

from moonlighter.discovery.collection import collect_raw_jobs
from moonlighter.discovery.sources.base import RawJob


async def _collect(config):
    """Runs collect_raw_jobs with no HTTP-registry scanners and no LinkedIn jobs,
    isolating the Gupy dispatch branch.
    """
    with (
        patch("moonlighter.discovery.collection.build_http_scanners", return_value={}),
        patch("moonlighter.discovery.collection.discover_entry_points", return_value=[]),
    ):
        return await collect_raw_jobs("engineer", config, {})


async def test_collect_raw_jobs_skips_gupy_by_default():
    with patch("moonlighter.discovery.portals.GupyScanner") as mock_gupy:
        mock_gupy.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    mock_gupy.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_gupy_when_config_enabled():
    gupy_job = RawJob(
        source="gupy", company="acme", title="Eng", url="https://acme.gupy.io/1", description="d"
    )
    with patch("moonlighter.discovery.portals.GupyScanner") as mock_gupy:
        mock_gupy.return_value.scan = AsyncMock(return_value=[gupy_job])
        raw_jobs, _ = await _collect({"scan_gupy": True})
    mock_gupy.return_value.scan.assert_awaited_once_with(keywords="engineer", stats=ANY)
    assert raw_jobs == [gupy_job]


async def test_collect_raw_jobs_skips_remoteok_by_default():
    with patch("moonlighter.discovery.portals.RemoteOKScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    mock_scanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_remoteok_when_config_enabled():
    # Title must match the "engineer" keyword _collect() passes through, or the
    # dispatcher's own keyword filter (added alongside the config gate) drops it.
    job = RawJob(source="remoteok", company="Acme", title="Engineer", url="https://remoteok.com/1")
    with patch("moonlighter.discovery.portals.RemoteOKScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_remoteok": True})
    mock_scanner.return_value.scan.assert_awaited_once_with(stats=ANY)
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_remotive_by_default():
    with patch("moonlighter.discovery.portals.RemotiveScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    mock_scanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_remotive_when_config_enabled():
    job = RawJob(source="remotive", company="Acme", title="Engineer", url="https://remotive.com/1")
    with patch("moonlighter.discovery.portals.RemotiveScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_remotive": True})
    mock_scanner.return_value.scan.assert_awaited_once_with(category=None, stats=ANY)
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_wwr_by_default():
    with patch("moonlighter.discovery.portals.WeWorkRemotelyScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    mock_scanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_wwr_when_config_enabled():
    job = RawJob(
        source="weworkremotely",
        company="Acme",
        title="Engineer",
        url="https://weworkremotely.com/1",
    )
    with patch("moonlighter.discovery.portals.WeWorkRemotelyScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_wwr": True})
    mock_scanner.return_value.scan.assert_awaited_once_with(category=None, stats=ANY)
    assert raw_jobs == [job]


async def test_collect_raw_jobs_skips_hn_whoishiring_by_default():
    with patch("moonlighter.discovery.portals.HNWhoIsHiringScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, _ = await _collect({})
    mock_scanner.return_value.scan.assert_not_called()
    assert raw_jobs == []


async def test_collect_raw_jobs_calls_hn_whoishiring_when_config_enabled():
    job = RawJob(
        source="hn_whoishiring",
        company="Acme",
        title="Engineer",
        url="https://news.ycombinator.com/item?id=1",
    )
    with patch("moonlighter.discovery.portals.HNWhoIsHiringScanner") as mock_scanner:
        mock_scanner.return_value.scan = AsyncMock(return_value=[job])
        raw_jobs, _ = await _collect({"scan_hn_whoishiring": True})
    mock_scanner.return_value.scan.assert_awaited_once_with(stats=ANY)
    assert raw_jobs == [job]
