"""Sources with no listing: a registered checker plugin, or a human confirming the link."""

from unittest.mock import AsyncMock, patch

from moonlighter.discovery.sources.base import RawJob
from moonlighter.discovery.staleness import find_stale_jobs
from tests.discovery.staleness.fake_jobs import CHECKERS, CONFIG, make_job, make_scanner

ACME_URL = "https://acme-ats.example/jobs/1"


async def test_unsupported_source_reports_each_job_for_a_human_to_confirm():
    """A manual job has no listing to diff against: the person checks the link.

    Alberto's rule, 2026-08-24 — a company name alone gave them nothing to open.
    """
    job = make_job(source="manual", company="somewhere", url="https://x.com/1")
    result = await find_stale_jobs({("manual", "somewhere"): [job]}, {}, CONFIG)
    assert result.stale == []
    assert result.stale_by_age == []
    assert result.unverifiable == [job]
    assert result.failed_companies == []


async def test_registered_checker_plugin_is_called_for_its_source():
    """A source with no listing support (e.g. LinkedIn) can be handled by a plugin.

    The checker is registered via the moonlighter.staleness_checkers entry_points group — see
    docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md. Never hardcoded by
    source name here: any plugin-registered source works.
    """
    job = make_job(source="acme_ats", company="acme", url=ACME_URL)
    fake_checker = AsyncMock()
    with patch(CHECKERS, return_value={"acme_ats": fake_checker}):
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    fake_checker.assert_called_once_with("acme", [job], CONFIG, result)
    assert result.failed_companies == []


async def test_no_registered_checker_falls_through_to_no_listing_check():
    """Same as the unsupported-source test, but explicit about the plugin lookup.

    "No plugin installed for this source" is the steady state for the public repo alone, with
    no private checker plugin present. The patch is asserted consulted: a patch that is never
    read would leave this test green for a lookup that moved elsewhere.
    """
    job = make_job(source="acme_ats", company="acme", url=ACME_URL)
    with patch(CHECKERS, return_value={}) as discover_checkers:
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    discover_checkers.assert_called_once_with("moonlighter.staleness_checkers")
    assert result.stale == []
    assert result.unverifiable == [job]
    assert result.failed_companies == []


async def test_checker_plugin_exception_marks_company_failed_not_stale():
    """An unguarded exception from an untrusted, plugin-provided checker must not propagate.

    It is caught the same way a first-party listing-scanner failure is, and must not abort
    other (source, company) groups.
    """
    failing_job = make_job(source="acme_ats", company="acme", url=ACME_URL)
    greenhouse_job = make_job(2, source="greenhouse", company="stripe", url="https://x.com/1")
    fake_checker = AsyncMock(side_effect=RuntimeError("boom"))
    scanners = {
        "greenhouse": make_scanner(
            [RawJob(source="greenhouse", company="stripe", title="Eng", url="https://x.com/1")]
        )
    }
    with patch(CHECKERS, return_value={"acme_ats": fake_checker}):
        result = await find_stale_jobs(
            {
                ("acme_ats", "acme"): [failing_job],
                ("greenhouse", "stripe"): [greenhouse_job],
            },
            scanners,
            CONFIG,
        )
    assert result.stale == []
    assert result.failed_companies == ["acme"]
    scanners["greenhouse"].scan.assert_awaited_once()


async def test_checker_plugin_exception_after_partial_failure_does_not_duplicate():
    """The dispatcher must not list a company twice when the checker already did.

    A checker may add the company to failed_companies before raising (a partial per-job
    failure inside the checker itself, as the real LinkedIn checker's own per-job try/except
    does).
    """
    job = make_job(source="acme_ats", company="acme", url=ACME_URL)

    async def flaky_checker(company, jobs, config, result):  # noqa: PLR0917 - the plugin protocol
        result.failed_companies.append(company)
        raise RuntimeError("boom after partial failure")

    with patch(CHECKERS, return_value={"acme_ats": flaky_checker}):
        result = await find_stale_jobs({("acme_ats", "acme"): [job]}, {}, CONFIG)
    assert result.failed_companies == ["acme"]
