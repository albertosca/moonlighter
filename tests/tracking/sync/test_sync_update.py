"""A sync update is a SyncUpdate, and the CLI's JSON for it is the dict it always was."""

from types import SimpleNamespace

from moonlighter.tracking.sync.report import (
    SyncUpdate,
    make_suggestion,
    make_update,
    sync_update_to_dict,
)

CLASSIFICATION = {
    "type": "interview",
    "stage": "tech",
    "company": "Email Co",
    "job_title": "Email Title",
    "summary": "Interview.",
}
APPLICATION = SimpleNamespace(job_id=7, job=SimpleNamespace(company="Acme", title="Staff Engineer"))


def test_a_matched_update_carries_the_job_and_serializes_without_suggestion_keys():
    update = make_update(CLASSIFICATION, "ref", APPLICATION, status_advanced=True)

    assert isinstance(update, SyncUpdate)
    assert sync_update_to_dict(update) == {
        "job_id": 7,
        "status_advanced": True,
        "company": "Acme",
        "title": "Staff Engineer",
        "type": "interview",
        "stage": "tech",
        "match_type": "ref",
        "summary": "Interview.",
    }


def test_an_unmatched_update_falls_back_to_what_the_email_says():
    update = make_update(CLASSIFICATION, "uncertain")

    assert (update.job_id, update.company, update.title) == (None, "Email Co", "Email Title")
    assert update.message_type == "interview"
    assert update.needs_confirmation is False


def test_a_suggestion_names_the_job_to_confirm_and_adds_exactly_two_keys():
    update = make_suggestion(APPLICATION, CLASSIFICATION, "fuzzy")

    assert update.job_id is None
    assert (update.suggested_job_id, update.needs_confirmation) == (7, True)
    assert sync_update_to_dict(update) == {
        "job_id": None,
        "status_advanced": False,
        "company": "Email Co",
        "title": "Email Title",
        "type": "interview",
        "stage": "tech",
        "match_type": "fuzzy",
        "summary": "Interview.",
        "suggested_job_id": 7,
        "needs_confirmation": True,
    }


def test_only_an_advanced_update_names_a_job_to_promote():
    advanced = make_update(CLASSIFICATION, "ref", APPLICATION, status_advanced=True)
    unchanged = make_update(CLASSIFICATION, "ref", APPLICATION)

    assert advanced.advanced_job_id == 7
    assert unchanged.advanced_job_id is None
