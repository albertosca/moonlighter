"""Reading the application reference out of a reply's recipient addresses."""

import pytest
from moonlighter.tracking.sync.application_matching import extract_ref

from tests.tracking.tracking_settings import BASE_EMAIL


class TestExtractRef:
    def test_alias_with_ref_returns_ref(self):
        to_header = "candidaturas+x7k2mp@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "x7k2mp"

    def test_no_alias_returns_none(self):
        assert extract_ref(BASE_EMAIL, BASE_EMAIL) is None

    def test_empty_string_returns_none(self):
        assert extract_ref("", BASE_EMAIL) is None

    def test_unrelated_address_returns_none(self):
        assert extract_ref("other@example.com", BASE_EMAIL) is None

    def test_strips_display_name(self):
        to_header = "Alberto <candidaturas+abc123@gmail.com>"
        assert extract_ref(to_header, BASE_EMAIL) == "abc123"

    def test_multiple_recipients_finds_alias(self):
        to_header = "hr@acme.com, candidaturas+zz9900@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "zz9900"

    def test_base_address_without_plus_returns_none(self):
        to_header = "candidaturas@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) is None

    def test_different_domain_returns_none(self):
        to_header = "candidaturas+ref123@hotmail.com"
        assert extract_ref(to_header, BASE_EMAIL) is None

    def test_ref_with_special_chars_in_urlsafe_b64(self):
        to_header = "candidaturas+Ab-_12@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "Ab-_12"

    def test_multiple_plus_signs_ref_includes_everything_after_first_plus(self):
        """Documents the actual partition behavior: only the FIRST '+' splits
        local-part from ref, so a second '+' becomes part of the ref value
        itself rather than being treated as a delimiter.
        """
        to_header = "candidaturas+ref+extra@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "ref+extra"

    def test_uppercase_local_and_domain_still_matches(self):
        to_header = "CANDIDATURAS+REF123@GMAIL.COM"
        assert extract_ref(to_header, BASE_EMAIL) == "REF123"

    def test_leading_trailing_whitespace_around_address_is_tolerated(self):
        to_header = "   candidaturas+ws001@gmail.com   "
        assert extract_ref(to_header, BASE_EMAIL) == "ws001"

    def test_whitespace_inside_angle_brackets_is_tolerated(self):
        to_header = "Alberto < candidaturas+ab001@gmail.com >"
        assert extract_ref(to_header, BASE_EMAIL) == "ab001"

    def test_injection_like_ref_is_extracted_verbatim(self):
        """The ref is a bare local-part token: anything an attacker puts after
        the '+' (short of '@' or ',') comes back verbatim. This is safe because
        callers only ever use it for an EXACT equality lookup against
        Application.email_ref (see _match_by_ref) — never interpolated into a
        query or command, so there is no injection surface here.
        """
        to_header = "candidaturas+'; DROP TABLE apps;--@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "'; DROP TABLE apps;--"

    def test_subdomain_suffix_does_not_match_base_domain(self):
        """'gmail.com.evil.com' must never be treated as 'gmail.com' — the
        security property extract_ref exists for (S-06: unspoofable +ref
        signal) requires the domain comparison to_header be an exact match, not a
        suffix/substring check.
        """
        to_header = "candidaturas+ref@gmail.com.evil.com"
        assert extract_ref(to_header, BASE_EMAIL) is None

    def test_base_domain_as_suffix_of_attacker_local_part_does_not_match(self):
        """An attacker-chosen local part that merely CONTAINS the real local
        part is not a match — comparison is on the full local part before '+',
        not a substring/suffix check.
        """
        to_header = "evilcandidaturas+ref@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) is None

    def test_none_to_field_returns_none(self):
        assert extract_ref(None, BASE_EMAIL) is None  # type: ignore[arg-type]

    def test_first_matching_recipient_wins_when_several_match(self):
        """Multiple recipients could, in principle, both match the base
        address with different refs (e.g. forwarded/CC'd copies) — the first
        one found in iteration order is returned, deterministically.
        """
        to_header = "candidaturas+first@gmail.com, candidaturas+second@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == "first"

    @pytest.mark.parametrize(
        "to_header",
        [
            "recruiter@acme.com",
            "candidaturas@othermail.com",
            "candidaturas+ref@yahoo.com",
            "notcandidaturas+ref@gmail.com",
            "candidaturas.x+ref@gmail.com",
            "random text with no email at all",
            ", , ,",
        ],
    )
    def test_no_false_extraction_for_non_matching_input(self, to_header):
        """Property: for any To-field that does not contain a genuine alias of
        base_address, extract_ref must return None — never fabricate a ref
        from an unrelated address. This is the core anti-spoofing guarantee.
        """
        assert extract_ref(to_header, BASE_EMAIL) is None

    @pytest.mark.parametrize("reference", ["a", "x7k2mp", "AB-cd_12", "123456", "r" * 64])
    def test_round_trips_ref_for_well_formed_alias(self, reference):
        """Property: for a well-formed alias of base_address, extract_ref
        recovers exactly the ref that was embedded — no truncation, no
        mangling, for a range of ref shapes.
        """
        to_header = f"candidaturas+{reference}@gmail.com"
        assert extract_ref(to_header, BASE_EMAIL) == reference


def test_extract_ref_skips_wrong_base_with_plus():
    """Address with +ref but a different base → continues and returns None (84->loop)."""
    assert extract_ref("someoneelse+abc@gmail.com", BASE_EMAIL) is None
