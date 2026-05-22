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
