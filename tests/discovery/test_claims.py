"""The URLs an earlier scan claimed are dropped, whatever their tracking suffix."""

from moonlighter.core.db import ScanLog, init_db
from moonlighter.discovery.claims import claim_url, drop_already_seen
from moonlighter.discovery.sources.base import RawJob


def test_drop_already_seen_matches_across_apply_suffix(temporary_database):
    init_db()
    ScanLog.create(job_url="https://x.recruitee.com/o/dev/c/new", source="recruitee")
    raw = RawJob(source="recruitee", company="x", title="Dev", url="https://x.recruitee.com/o/dev")
    assert drop_already_seen([raw]) == []


def test_claim_url_reserves_once_and_refuses_the_second_claim(temporary_database):
    init_db()
    assert claim_url("https://x.example/job", "manual") is True
    assert claim_url("https://x.example/job", "greenhouse") is False
    assert ScanLog.get(ScanLog.job_url == "https://x.example/job").source == "manual"
