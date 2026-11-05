import blocklist_candidates
import pytest

from moonlighter.core.db import init_db
from tests.scripts.build_blocklist.harness import scored


@pytest.fixture(autouse=True)
def _database(temporary_database):
    init_db()


def test_titles_are_grouped_by_company_and_sorted_within_it():
    scored("Beta", "Zeta", 1.0)
    scored("Acme", "Beta role", 2.0)
    scored("Acme", "Alpha role", 2.0)

    assert blocklist_candidates.fetch_low_scorers(3.0, None) == {
        "Acme": ["Alpha role", "Beta role"],
        "Beta": ["Zeta"],
    }
    assert list(blocklist_candidates.fetch_low_scorers(3.0, None)) == ["Acme", "Beta"]


@pytest.mark.parametrize(
    ("title", "score", "fields", "kept"),
    [
        ("edge of the threshold", 3.0, {}, True),
        ("above the threshold", 3.1, {}, False),
        ("zero is a failed evaluation", 0, {}, False),
        ("unscored", None, {}, False),
        ("not archived", 1.0, {"status": "new"}, False),
        ("no notes", 1.0, {"score_notes": None}, False),
        ("failed evaluation", 1.0, {"score_notes": "evaluation error: timeout"}, False),
        ("skipped by title", 1.0, {"score_notes": "title filtered: 'x'"}, False),
        ("failed retry", 1.0, {"score_notes": "reevaluate_error: boom"}, False),
        ("prefix only", 1.0, {"score_notes": "was an evaluation error once"}, True),
    ],
)
def test_which_jobs_count_as_genuinely_evaluated(title, score, fields, *, kept):
    scored("Acme", title, score, **fields)

    assert blocklist_candidates.fetch_low_scorers(3.0, None) == ({"Acme": [title]} if kept else {})


def test_the_company_argument_narrows_the_result_and_the_threshold_moves_the_bound():
    scored("Acme", "Low", 1.0)
    scored("Acme", "Mid", 4.0)
    scored("Beta", "Low too", 1.0)

    assert blocklist_candidates.fetch_low_scorers(5.0, "Acme") == {"Acme": ["Low", "Mid"]}
    assert blocklist_candidates.fetch_low_scorers(5.0, "Nobody") == {}
    assert blocklist_candidates.fetch_low_scorers(5.0, "") == {
        "Acme": ["Low", "Mid"],
        "Beta": ["Low too"],
    }
