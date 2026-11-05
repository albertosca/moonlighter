"""job_to_dict projects every Job column into the JSON document, and emit writes it as one stdout line."""

import json
from datetime import datetime

from moonlighter.core.cli import emit, job_to_dict
from moonlighter.core.db import Job, init_db


def test_job_to_dict_projects_every_column_with_iso_datetimes(temporary_database):
    init_db()
    job = Job.create(
        source="greenhouse",
        company="Acme",
        title="Staff Engineer",
        url="https://boards.greenhouse.io/acme/jobs/1",
        score=8.5,
        status="new",
        posted_at=datetime(2026, 9, 1, 12, 0, 0),  # noqa: DTZ001 - the database stores naive local time
    )
    payload = job_to_dict(job)
    assert payload["id"] == job.id
    assert payload["company"] == "Acme"
    assert payload["score"] == 8.5
    assert payload["posted_at"] == "2026-09-01T12:00:00"
    assert payload["closed_at"] is None
    # Every persisted column is present: a consumer never has to go back to the DB.
    for column in (
        "source",
        "title",
        "url",
        "location",
        "remote_type",
        "description",
        "score_notes",
        "caveats",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_source",
        "salary_notes",
        "status",
        "found_at",
    ):
        assert column in payload


def test_emit_writes_exactly_one_json_line_to_stdout_and_returns_the_code(capsys):
    code = emit({"kind": "evaluated", "saved": []}, 0)
    out, error_output = capsys.readouterr()
    assert code == 0
    assert error_output == ""
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert json.loads(out) == {"kind": "evaluated", "saved": []}
