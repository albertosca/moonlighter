"""The Job factory that the db tests share: the four required fields, each overridable."""

from moonlighter.core.db import Job


def make_job(**overrides):
    """Helper: creates a Job with minimal defaults, overridden by overrides."""
    defaults = {
        "source": "greenhouse",
        "company": "Stripe",
        "title": "Senior Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/123",
    }
    defaults.update(overrides)
    return Job.create(**defaults)
