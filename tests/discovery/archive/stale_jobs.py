"""A job row for the archive tests."""

from moonlighter.core.db import Job


def make_stale_job(temporary_database, **overrides):
    defaults = {
        "source": "greenhouse",
        "company": "acme",
        "title": "Engineer",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "status": "new",
    }
    defaults.update(overrides)
    return Job.create(**defaults)
