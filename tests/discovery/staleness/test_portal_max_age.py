"""How find_stale_jobs reads the portal_max_age_days setting."""

from datetime import datetime, timedelta

import pytest

from moonlighter.core.config.errors import ConfigError
from moonlighter.core.config.loading import build_config
from moonlighter.discovery.staleness import find_stale_jobs
from tests.discovery.staleness.fake_jobs import make_job


def _aged_job(days):
    job = make_job(1, source="remoteok")
    job.found_at = datetime.now() - timedelta(days=days)  # noqa: DTZ005 - the database stores naive local time
    return job


@pytest.mark.parametrize("age_limit", ["30", None, "soon"])
def test_an_age_limit_that_is_not_an_integer_is_refused_at_load(age_limit):
    with pytest.raises(ConfigError, match="portal_max_age_days"):
        build_config({"portal_max_age_days": age_limit})


async def test_a_negative_age_limit_archives_nothing_by_age():
    old = _aged_job(400)
    result = await find_stale_jobs(
        {("remoteok", "acme"): [old]}, {}, build_config({"portal_max_age_days": -5})
    )
    assert result.stale_by_age == []
    assert result.failed_companies == ["1 remoteok job(s) (portal feed, no per-company listing)"]
