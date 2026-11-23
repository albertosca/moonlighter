"""A job added by URL from a supported ATS is checked against that ATS's board.

Found 2026-11-16 (Encora #8314): a manual job pasted from a Greenhouse URL had no listing
to diff against, so it stayed open after the posting left the board. The comparison is by
posting id, never by URL: Greenhouse's absolute_url can point at the company's own careers
site (?gh_jid=<id>), and a pasted URL can use boards. where the listing uses job-boards.
"""

from moonlighter.discovery.sources.base import RawJob, SourceStats
from moonlighter.discovery.staleness import find_stale_jobs
from tests.discovery.staleness.fake_jobs import CONFIG, make_job, make_scanner

ENCORA = "Encora (Coforge)"
GH_URL = "https://job-boards.greenhouse.io/encora10/jobs/5244244007"
ASHBY_ID = "d1356390-eb3b-481e-930c-809fef8f74d8"


def _listed(source, slug, *urls):
    return [RawJob(source=source, company=slug, title="Eng", url=url) for url in urls]


def _manual(url, *, company=ENCORA, job_id=1):
    return make_job(job_id, source="manual", company=company, url=url)


async def _check(jobs, scanners):
    company = jobs[0].company
    return await find_stale_jobs({("manual", company): jobs}, scanners, CONFIG)


async def test_a_manual_greenhouse_job_missing_from_its_board_is_stale():
    job = _manual(GH_URL)
    scanner = make_scanner(
        _listed("greenhouse", "encora10", "https://job-boards.greenhouse.io/encora10/jobs/1")
    )

    result = await _check([job], {"greenhouse": scanner})

    assert result.stale == [job]
    assert result.unverifiable == []
    assert scanner.scan.call_args.args[0] == ["encora10"]


async def test_a_manual_greenhouse_job_still_listed_under_the_company_site_stays_open():
    job = _manual(GH_URL)
    listing = _listed("greenhouse", "encora10", "https://careers.encora.com/jobs?gh_jid=5244244007")

    result = await _check([job], {"greenhouse": make_scanner(listing)})

    assert result.stale == []
    assert result.unverifiable == []
    assert result.failed_companies == []


async def test_a_pasted_boards_host_matches_a_job_boards_listing():
    job = _manual("https://boards.greenhouse.io/encora10/jobs/5244244007?gh_src=abc")
    listing = _listed("greenhouse", "encora10", GH_URL)

    result = await _check([job], {"greenhouse": make_scanner(listing)})

    assert result.stale == []


async def test_a_manual_ashby_job_missing_from_its_board_is_stale_and_a_listed_one_stays():
    gone = _manual(
        "https://jobs.ashbyhq.com/3y-health/aaaaaaaa-0000-0000-0000-000000000000",
        company="3Y Health",
    )
    listed = _manual(
        f"https://jobs.ashbyhq.com/3y-health/{ASHBY_ID}/application", company="3Y Health", job_id=2
    )
    scanner = make_scanner(
        _listed("ashby", "3y-health", f"https://jobs.ashbyhq.com/3y-health/{ASHBY_ID}")
    )

    result = await _check([gone, listed], {"ashby": scanner})

    assert result.stale == [gone]
    assert scanner.scan.call_args.args[0] == ["3y-health"]


async def test_a_url_that_matches_no_supported_board_still_asks_the_person():
    job = _manual("https://www.workatastartup.com/jobs/73764", company="Nango")
    scanner = make_scanner([])

    result = await _check([job], {"greenhouse": scanner, "ashby": scanner})

    assert result.unverifiable == [job]
    assert result.stale == []
    scanner.scan.assert_not_called()


async def test_an_eu_greenhouse_board_is_left_to_the_person():
    # The scanner reads only the US boards API, so it cannot see an EU board.
    job = _manual(
        "https://job-boards.eu.greenhouse.io/teachablecareers/jobs/4913809101", company="Teachable"
    )
    scanner = make_scanner([])

    result = await _check([job], {"greenhouse": scanner})

    assert result.unverifiable == [job]
    scanner.scan.assert_not_called()


async def test_a_failed_board_fetch_leaves_the_job_untouched_and_names_the_company():
    class _Failing:
        async def scan(self, company_slugs, **keyword_arguments):
            keyword_arguments["stats"]["greenhouse"] = SourceStats(companies=1, jobs=0, errors=1)
            return []

    job = _manual(GH_URL)

    result = await _check([job], {"greenhouse": _Failing()})

    assert result.stale == []
    assert result.unverifiable == []
    assert result.failed_companies == [ENCORA]


async def test_a_listing_url_with_no_posting_id_archives_nothing():
    # Without an id for every open posting, "missing" cannot be proven.
    job = _manual(GH_URL)
    listing = _listed("greenhouse", "encora10", "https://careers.encora.com/open-roles/backend")

    result = await _check([job], {"greenhouse": make_scanner(listing)})

    assert result.stale == []
    assert result.failed_companies == [ENCORA]
