"""Job and Application rows for the tracking tests that read the pipeline."""

from moonlighter.core.db import Application, Job


def make_job(temporary_database, **overrides):
    defaults = {
        "source": "greenhouse",
        "company": "Anthropic",
        "title": "Senior Engineer",
        "url": "https://boards.greenhouse.io/anthropic/jobs/1",
    }
    defaults.update(overrides)
    return Job.create(**defaults)


def make_application(job, **overrides):
    defaults = {"status": "submitted"}
    defaults.update(overrides)
    return Application.create(job=job, **defaults)
