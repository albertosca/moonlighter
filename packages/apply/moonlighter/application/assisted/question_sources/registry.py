"""The ordered list of form-question sources; the first that matches a job wins."""

from moonlighter.application.assisted.question_sources.base import QuestionSource, SourceMatch
from moonlighter.application.assisted.question_sources.greenhouse import GreenhouseSource
from moonlighter.application.assisted.question_sources.inhire import InHireSource
from moonlighter.application.assisted.question_sources.lever import LeverSource
from moonlighter.application.assisted.question_sources.recruitee import RecruiteeSource
from moonlighter.application.assisted.question_sources.workable import WorkableSource
from moonlighter.core.db import Job

SOURCES: tuple[QuestionSource, ...] = (
    GreenhouseSource(),
    RecruiteeSource(),
    WorkableSource(),
    LeverSource(),
    InHireSource(),
)


def find_match(job: Job) -> SourceMatch | None:
    for source in SOURCES:
        if (match := source.match(job)) is not None:
            return match
    return None
