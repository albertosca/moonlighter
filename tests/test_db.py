import os
import pytest
from candidatador.db import init_db, Job, Application, ScanLog


def test_init_creates_tables(tmp_db):
    os.environ["CANDIDATADOR_DB_PATH"] = tmp_db
    init_db()
    # Tables exist and accept writes
    job = Job.create(
        source="greenhouse",
        company="Stripe",
        title="Senior Engineer",
        url="https://boards.greenhouse.io/stripe/jobs/123",
    )
    assert job.id is not None
    assert job.status == "new"


def test_scan_log_dedup(tmp_db):
    os.environ["CANDIDATADOR_DB_PATH"] = tmp_db
    init_db()
    ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")
    urls = {row.job_url for row in ScanLog.select()}
    assert "https://example.com/job/1" in urls
    # Second insert with same URL should raise IntegrityError
    with pytest.raises(Exception):
        ScanLog.create(job_url="https://example.com/job/1", source="greenhouse")
