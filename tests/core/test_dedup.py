"""The content key: what makes two postings the same job whatever their URLs."""

import pytest

from moonlighter.core.dedup import PostingKey, description_hash, normalize_text, posting_key


def test_normalize_collapses_case_tags_whitespace_and_punctuation():
    assert normalize_text("<p>Senior  Engineer,\n(Remote)</p>&amp;") == "senior engineer remote"


def test_normalize_keeps_accented_letters():
    assert normalize_text("Engenheiro de Dados — São Paulo") == "engenheiro de dados são paulo"


@pytest.mark.parametrize("empty", [None, "", "   \n\t", "<div><br/></div>", "---"])
def test_empty_text_has_no_hash_and_no_key(empty):
    assert description_hash(empty) is None
    assert posting_key("Acme", "Engineer", empty) is None


def test_two_texts_differing_only_in_whitespace_and_case_share_a_hash():
    assert description_hash("We build  RAILS apps.") == description_hash("we build rails apps")


def test_different_texts_have_different_hashes():
    assert description_hash("Remote in Brazil") != description_hash("Remote in Europe")


def test_posting_key_normalizes_company_and_title():
    key = posting_key(" Tether ", "AgenticOps  Engineer", "Same text")
    assert key == PostingKey("tether", "agenticops engineer", description_hash("Same text"))
