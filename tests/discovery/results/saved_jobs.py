"""Stored jobs for the render-counts tests."""

from moonlighter.core.db import Job


def saved_job(url, *, status="new", score=8.0, score_notes="match"):
    return Job.create(
        source="greenhouse",
        company="Acme",
        title="Engineer",
        url=url,
        status=status,
        score=score,
        score_notes=score_notes,
    )
