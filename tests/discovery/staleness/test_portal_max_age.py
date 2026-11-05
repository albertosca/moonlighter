"""How find_stale_jobs reads the portal_max_age_days setting."""

from datetime import datetime, timedelta

import pytest
from moonlighter.discovery.staleness import find_stale_jobs

from tests.discovery.staleness.fake_jobs import make_job


def _aged_job(days):
    job = make_job(1, source="remoteok")
    job.found_at = datetime.now() - timedelta(days=days)  # noqa: DTZ005 - the database stores naive local time
    return job


async def test_a_string_age_limit_is_read_as_a_number_of_days():
    old = _aged_job(45)
    result = await find_stale_jobs({("remoteok", "acme"): [old]}, {}, {"portal_max_age_days": "30"})
    assert result.stale_by_age == [old]


async def test_a_negative_age_limit_archives_nothing_by_age():
    old = _aged_job(400)
    result = await find_stale_jobs({("remoteok", "acme"): [old]}, {}, {"portal_max_age_days": -5})
    assert result.stale_by_age == []
    assert result.failed_companies == ["1 remoteok job(s) (portal feed, no per-company listing)"]


async def test_a_null_age_limit_archives_nothing_by_age():
    old = _aged_job(400)
    result = await find_stale_jobs({("remoteok", "acme"): [old]}, {}, {"portal_max_age_days": None})
    assert result.stale_by_age == []


async def test_an_age_limit_that_is_not_a_number_raises_value_error():
    with pytest.raises(ValueError, match="invalid literal"):
        await find_stale_jobs(
            {("remoteok", "acme"): [_aged_job(1)]}, {}, {"portal_max_age_days": "soon"}
        )
