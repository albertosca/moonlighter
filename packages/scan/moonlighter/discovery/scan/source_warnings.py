"""The report line for each source that errored or came back empty."""

from moonlighter.discovery.sources.base import ScanStats, SourceStats


def _is_healthy(source_stats: SourceStats) -> bool:
    return source_stats.errors == 0 and source_stats.jobs > 0


def _scope(source_stats: SourceStats) -> str:
    if not source_stats.companies:
        return ""
    company_word = "company" if source_stats.companies == 1 else "companies"
    return f" from {source_stats.companies} {company_word}"


def _error_suffix(source_stats: SourceStats) -> str:
    if not source_stats.errors:
        return ""
    error_word = "error" if source_stats.errors == 1 else "errors"
    return f" ({source_stats.errors} fetch {error_word})"


def stats_warnings(stats: ScanStats) -> list[str]:
    """One report line per source that errored or came back empty.

    Zero-from-N with no errors still earns a line: it is exactly the shape the
    dead Ashby GraphQL API produced for weeks (HTTP 200, error payload, zero
    jobs). A healthy source adds nothing.
    """
    return [
        f"⚠️  {source}: {source_stats.jobs} jobs{_scope(source_stats)}{_error_suffix(source_stats)}"
        for source, source_stats in sorted(stats.items())
        if not _is_healthy(source_stats)
    ]
