"""find_original: the stored job a new posting is a copy of."""

from datetime import datetime

from moonlighter.core.db import Job, init_db
from moonlighter.core.duplicates import find_original, group_duplicates

TEXT = "We build Rails apps. Remote in Brazil."


def _job(number, **fields):
    defaults = {
        "source": "recruitee",
        "company": "Tether",
        "title": "Eng",
        "url": f"https://x/{number}",
        "description": TEXT,
    }
    return Job.create(**{**defaults, **fields})


def test_same_company_title_and_text_is_a_copy(temporary_database):
    init_db()
    original = _job(1)
    assert find_original(" tether ", "ENG", TEXT.upper()).id == original.id


def test_same_title_other_text_is_not_a_copy(temporary_database):
    init_db()
    _job(1)
    assert find_original("Tether", "Eng", "Remote in Europe") is None


def test_same_text_other_company_or_title_is_not_a_copy(temporary_database):
    init_db()
    _job(1)
    assert find_original("Other", "Eng", TEXT) is None
    assert find_original("Tether", "Designer", TEXT) is None


def test_an_empty_description_never_matches(temporary_database):
    init_db()
    _job(1, description="")
    assert find_original("Tether", "Eng", "") is None
    assert find_original("Tether", "Eng", None) is None


def test_the_original_is_the_lowest_id_that_is_not_itself_a_copy(temporary_database):
    init_db()
    first = _job(1)
    _job(2, duplicate_of=first)
    assert find_original("Tether", "Eng", TEXT).id == first.id


def test_a_lower_id_copy_never_wins(temporary_database):
    init_db()
    later_original = _job(2)
    _job(1, duplicate_of=later_original)
    assert find_original("Tether", "Eng", TEXT).id == later_original.id


def test_the_applied_row_is_kept_over_a_higher_score(temporary_database):
    init_db()
    high = _job(1, score=9.0)
    applied = _job(2, score=4.0)
    groups = group_duplicates([high, applied], applied_job_ids={applied.id})
    assert [(group.kept.id, [copy.id for copy in group.copies]) for group in groups] == [
        (applied.id, [high.id])
    ]


def test_without_applications_the_highest_score_then_the_lowest_id(temporary_database):
    init_db()
    low = _job(1, score=5.0)
    high = _job(2, score=8.0)
    tie = _job(3, score=8.0)
    unscored = _job(4, score=None)
    groups = group_duplicates([unscored, low, tie, high], applied_job_ids=set())
    assert groups[0].kept.id == high.id
    assert sorted(copy.id for copy in groups[0].copies) == [low.id, tie.id, unscored.id]


def test_two_applied_rows_are_never_copies(temporary_database):
    init_db()
    first, second, third = _job(1), _job(2), _job(3)
    groups = group_duplicates([first, second, third], applied_job_ids={first.id, second.id})
    assert [copy.id for copy in groups[0].copies] == [third.id]


def test_a_group_of_applied_rows_only_is_left_alone(temporary_database):
    init_db()
    first, second = _job(1), _job(2)
    assert group_duplicates([first, second], applied_job_ids={first.id, second.id}) == []


def test_singletons_rows_without_text_and_existing_copies_form_no_group(temporary_database):
    init_db()
    alone = _job(1)
    empty_one = _job(2, description="", title="Other")
    empty_two = _job(3, description="", title="Other")
    already = _job(4, duplicate_of=alone)
    assert group_duplicates([alone, empty_one, empty_two, already], applied_job_ids=set()) == []


def test_a_posting_known_to_be_gone_is_no_original(temporary_database):
    init_db()
    _job(1, status="archived", closed_at=datetime(2026, 5, 1))  # noqa: DTZ001 - naive local time
    assert find_original("Tether", "Eng", TEXT) is None


def test_a_repost_after_a_gone_original_becomes_the_original(temporary_database):
    init_db()
    _job(1, status="archived", closed_at=datetime(2026, 5, 1))  # noqa: DTZ001 - naive local time
    repost = _job(2)
    assert find_original("Tether", "Eng", TEXT).id == repost.id


def test_an_original_archived_by_its_score_still_counts(temporary_database):
    init_db()
    original = _job(1, status="archived", score=2.0)
    assert find_original("Tether", "Eng", TEXT).id == original.id
