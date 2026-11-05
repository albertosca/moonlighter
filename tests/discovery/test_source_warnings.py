"""One report line per source that errored or came back empty."""

from moonlighter.discovery.source_warnings import stats_warnings
from moonlighter.discovery.sources.base import ScanStats, SourceStats


def test_stats_warnings_flags_errors_and_empty_sources():
    stats: ScanStats = {
        "greenhouse": SourceStats(companies=3, jobs=17, errors=0),  # healthy → silent
        "ashby": SourceStats(companies=39, jobs=0, errors=39),  # broken → loud
        "workable": SourceStats(companies=12, jobs=0, errors=0),  # empty → loud
        "remoteok": SourceStats(companies=0, jobs=0, errors=1),  # portal error → loud
    }
    lines = stats_warnings(stats)
    assert lines == [
        "⚠️  ashby: 0 jobs from 39 companies (39 fetch errors)",
        "⚠️  remoteok: 0 jobs (1 fetch error)",
        "⚠️  workable: 0 jobs from 12 companies",
    ]


def test_stats_warnings_singularizes_one_company_and_one_error():
    """MINOR regression: 'from 1 companies' / '1 fetch errors' read as broken
    grammar -- singular counts must use the singular noun."""
    stats: ScanStats = {
        "greenhouse": SourceStats(companies=1, jobs=0, errors=1),
    }
    lines = stats_warnings(stats)
    assert lines == ["⚠️  greenhouse: 0 jobs from 1 company (1 fetch error)"]
