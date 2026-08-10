import pytest
from moonlighter.core.db import Application, Job, init_db


@pytest.fixture
def application_factory(tmp_db):
    """Creates an Application (with a backing Job) in a fresh per-test DB.

    Relies on the root `tmp_db` fixture to point MOONLIGHTER_DB_PATH at a temp
    file, then initializes the schema once per test. Each call makes its own
    Job (url must be unique), so multiple applications can be created safely.
    """
    init_db()
    count = 0

    def _make(**kwargs):
        nonlocal count
        count += 1
        job = Job.create(
            source="greenhouse",
            company="Anthropic",
            title="Senior Engineer",
            url=f"https://boards.greenhouse.io/anthropic/jobs/{count}",
        )
        defaults: dict = {"status": "submitted"}
        defaults.update(kwargs)
        return Application.create(job=job, **defaults)

    return _make
