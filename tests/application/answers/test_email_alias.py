import re

from moonlighter.application.answers.email_alias import (
    build_email_alias,
    is_email_label,
    new_email_ref,
)


def test_a_ref_carries_no_case_so_a_provider_cannot_change_it():
    for _ in range(200):
        ref = new_email_ref()
        assert ref == ref.lower()


def test_a_ref_avoids_characters_a_human_would_misread():
    banned = set("lo01")
    for _ in range(200):
        assert not (set(new_email_ref()) & banned)


def test_a_ref_is_eight_characters_of_the_expected_alphabet():
    assert re.fullmatch(r"[a-z2-9]{8}", new_email_ref())


def test_refs_do_not_repeat_in_practice():
    assert len({new_email_ref() for _ in range(500)}) == 500


def test_build_email_alias_formats_correctly():
    result = build_email_alias("candidaturas@gmail.com", "x7k2mp")
    assert result == "candidaturas+x7k2mp@gmail.com"


def test_build_email_alias_different_refs():
    assert build_email_alias("a@b.com", "abc") == "a+abc@b.com"
    assert build_email_alias("a@b.com", "xyz") == "a+xyz@b.com"


def test_is_email_label_matches_ptbr_hyphenated_required_label():
    """'E-mail*' (PT, hyphen, required asterisk) is the live shape that once
    needed a normalization fix — it must keep matching."""
    assert is_email_label("E-mail*")


def test_is_email_label_matches_plain_and_suffixed_labels():
    assert is_email_label("Email")
    assert is_email_label("Email address")


def test_is_email_label_rejects_labels_that_merely_start_with_the_word():
    assert not is_email_label("Emailing preferences")


def test_is_email_label_rejects_unrelated_labels():
    assert not is_email_label("Nome*")
    assert not is_email_label("Your email")  # anchored, like field_map's own rule
