"""collapse_duplicates: one posting per scan, whatever its URLs."""

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.scan.duplicates import collapse_duplicates
from moonlighter.discovery.sources.base import RawJob


def _raw(url, *, title="AgenticOps", description="Same text", company="Tether"):
    return RawJob(
        source="recruitee", company=company, title=title, url=url, description=description
    )


def test_three_slugs_with_one_text_become_one(temporary_database):
    init_db()
    raw_jobs = [_raw("https://x/a"), _raw("https://x/a-9"), _raw("https://x/a-10")]
    assert [raw.url for raw in collapse_duplicates(raw_jobs)] == ["https://x/a"]


def test_same_title_two_texts_stay_two():
    raw_jobs = [
        _raw("https://x/br", description="Remote in Brazil"),
        _raw("https://x/eu", description="Remote in Europe"),
    ]
    assert len(collapse_duplicates(raw_jobs)) == 2


def test_same_text_at_two_companies_stays_two():
    raw_jobs = [_raw("https://x/1", company="Tether"), _raw("https://x/2", company="Bitfinex")]
    assert len(collapse_duplicates(raw_jobs)) == 2


def test_empty_descriptions_are_never_collapsed():
    raw_jobs = [_raw("https://x/1", description=""), _raw("https://x/2", description=None)]
    assert len(collapse_duplicates(raw_jobs)) == 2


def test_the_order_is_kept(temporary_database):
    init_db()
    raw_jobs = [
        _raw("https://x/1", title="A"),
        _raw("https://x/2", title="B"),
        _raw("https://x/3", title="A"),
    ]
    assert [raw.url for raw in collapse_duplicates(raw_jobs)] == ["https://x/1", "https://x/2"]


def test_copies_of_a_stored_job_all_go_through_to_the_free_check(temporary_database):
    init_db()
    Job.create(
        source="recruitee",
        company="Tether",
        title="AgenticOps",
        url="https://x/a",
        description="Same text",
    )
    raw_jobs = [_raw("https://x/a-9"), _raw("https://x/a-10")]
    assert len(collapse_duplicates(raw_jobs)) == 2
