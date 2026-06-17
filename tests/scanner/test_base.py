from datetime import datetime

from candidatador.scanner.base import RawJob, normalize_remote_type


def test_rawjob_defaults():
    job = RawJob(source="greenhouse", company="Stripe", title="Eng", url="https://x.com")
    assert job.remote_type is None
    assert job.salary_source is None


def test_normalize_remote_type():
    assert normalize_remote_type("Remote - US") == "remote"
    assert normalize_remote_type("Hybrid, São Paulo") == "hybrid"
    assert normalize_remote_type("New York, NY") == "onsite"
    assert normalize_remote_type(None) is None


def test_normalize_remote_case_insensitive():
    assert normalize_remote_type("REMOTE") == "remote"
    assert normalize_remote_type("Remote") == "remote"


def test_normalize_hybrid_variations():
    assert normalize_remote_type("Hybrid, São Paulo") == "hybrid"
    assert normalize_remote_type("Hybrid-Remote") == "hybrid"


def test_normalize_onsite_in_office():
    assert normalize_remote_type("In-Office") == "onsite"


def test_normalize_onsite_on_site():
    assert normalize_remote_type("On-Site, NY") == "onsite"


def test_normalize_empty_string_returns_none():
    assert normalize_remote_type("") is None


def test_normalize_unknown_string_returns_onsite():
    assert normalize_remote_type("negotiable") == "onsite"


def test_normalize_us_only_string():
    assert normalize_remote_type("United States") == "onsite"


def test_rawjob_with_all_fields():
    now = datetime.now()
    job = RawJob(
        source="greenhouse",
        company="Stripe",
        title="Eng",
        url="https://x.com",
        location="Remote",
        remote_type="remote",
        description="desc",
        posted_at=now,
        salary_min=100000,
        salary_max=150000,
        salary_currency="USD",
        salary_source="stated",
    )
    assert job.salary_min == 100000
    assert job.salary_currency == "USD"
    assert job.posted_at == now


def test_rawjob_source_values():
    for source in ("greenhouse", "lever", "ashby", "linkedin"):
        job = RawJob(source=source, company="Co", title="Eng", url="https://x.com")
        assert job.source == source


def test_rawjob_posted_at_is_datetime():
    now = datetime.now()
    job = RawJob(source="greenhouse", company="Co", title="Eng", url="https://x.com", posted_at=now)
    assert isinstance(job.posted_at, datetime)
