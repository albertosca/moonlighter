"""find_original: the stored job a new posting is a copy of."""

from moonlighter.core.db import Job, init_db
from moonlighter.core.duplicates import find_original

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
