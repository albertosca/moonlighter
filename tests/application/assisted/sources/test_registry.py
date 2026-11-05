import pytest
from moonlighter.application.assisted.sources import registry
from moonlighter.core.db import Job

# (job.source, job.url, the one source name expected to match, or None).
# Every new source appends its URLs here: no URL may match two sources.
CASES = [
    ("greenhouse", "https://job-boards.greenhouse.io/gitlab/jobs/8503792002", "greenhouse"),
    ("manual", "https://boards.greenhouse.io/acme/jobs/1", "greenhouse"),
    ("recruitee", "https://curotec.recruitee.com/o/senior-android/c/new", "recruitee"),
    ("recruitee", "https://jobs.channable.com/o/x", "recruitee"),
    ("manual", "https://jobs.channable.com/o/x", None),
    ("smartrecruiters", "https://jobs.smartrecruiters.com/x/y", None),
    ("manual", "https://careers.acme.com/jobs/engineer", None),
    ("workable", "https://apply.workable.com/j/1378093793/apply", "workable"),
    ("manual", "https://apply.workable.com/devsu/j/C3DABE6A92/", "workable"),
    ("lever", "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd", "lever"),
    (
        "manual",
        "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply",
        "lever",
    ),
    ("lever", "https://jobs.eu.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd", None),
    ("inhire", "https://infleet.inhire.app/vagas/1a3ea3dc-5558-45b6-aecb-58e89f5af1dd", "inhire"),
    ("inhire", "https://infleet.inhire.app/sobre", None),
]


@pytest.mark.parametrize(("source", "url", "expected"), CASES)
def test_each_url_matches_the_expected_source(source, url, expected):
    match = registry.find_match(Job(source=source, url=url))
    assert (match.source.name if match else None) == expected


@pytest.mark.parametrize(("source", "url", "expected"), CASES)
def test_no_url_matches_two_sources(source, url, expected):
    job = Job(source=source, url=url)
    matching = [candidate.name for candidate in registry.SOURCES if candidate.match(job)]
    assert len(matching) <= 1, matching
