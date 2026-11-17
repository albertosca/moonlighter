"""The prefilter archives a copy of a stored job without an LLM call."""

from moonlighter.core.db import Job, init_db
from moonlighter.discovery.screening.prefilter import ScreeningRules, screen_chunk
from moonlighter.discovery.sources.base import RawJob

TEXT = "We build Rails apps for payments. Remote in Brazil."
RULES = ScreeningRules(blocklist=[], home_city=None, eligible_regions=())


def _raw(url, description=TEXT):
    return RawJob(
        source="recruitee",
        company="Tether",
        title="Eng",
        url=url,
        remote_type="remote",
        description=description,
    )


def _original():
    return Job.create(
        source="recruitee", company="Tether", title="Eng", url="https://x/1", description=TEXT
    )


def test_a_copy_is_archived_against_the_original(temporary_database):
    init_db()
    original = _original()
    saved, to_evaluate = screen_chunk([_raw("https://x/1-9")], RULES)
    assert to_evaluate == []
    copy = saved[0]
    assert (copy.status, copy.duplicate_of_id, copy.score_notes) == (
        "archived",
        original.id,
        f"duplicate of #{original.id}",
    )


def test_same_title_other_text_is_evaluated(temporary_database):
    init_db()
    _original()
    other = _raw("https://x/eu", description="We build Rails apps for payments. Remote in Europe.")
    saved, to_evaluate = screen_chunk([other], RULES)
    assert (saved, [raw.url for raw in to_evaluate]) == ([], ["https://x/eu"])
