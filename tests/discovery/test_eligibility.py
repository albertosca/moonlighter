"""Deterministic regional-eligibility classification from structured fields.

Provenance: live incident 2026-08-20/21 (job 7733 and the gitlab cluster) —
the eligibility hard filter lived only in the evaluator prompt, which sees the
DESCRIPTION; on boards like GitLab the region lives in the posting's location
field ("Bangalore, India"), which the LLM never saw. 32/32 gitlab jobs and
~2/3 of the whole queue were false positives, all cut by hand.

Alberto's rule: eligible = remote with an explicit eligible region
(BR/LATAM/Americas/global/worldwide) OR onsite in Belo Horizonte.
"""

from moonlighter.discovery.eligibility import (
    Eligibility,
    classify_location,
    eligible_regions_from,
)

# The regions that used to be hardcoded; now a profile setting (criteria.eligible_regions).
REGIONS = ("Brazil", "Brasil", "LATAM", "Latin America", "South America", "Americas", "worldwide")


class TestEligible:
    def test_belo_horizonte_onsite(self):
        assert (
            classify_location("Belo Horizonte, Brazil", "onsite", home_city="Belo Horizonte")
            is Eligibility.ELIGIBLE
        )

    def test_remote_worldwide(self):
        assert (
            classify_location("Remote - Worldwide", "remote", eligible_regions=REGIONS)
            is Eligibility.ELIGIBLE
        )

    def test_remote_latam(self):
        assert (
            classify_location("Remote (LATAM)", "remote", eligible_regions=REGIONS)
            is Eligibility.ELIGIBLE
        )

    def test_remote_brazil(self):
        assert (
            classify_location("Brazil", "remote", eligible_regions=REGIONS) is Eligibility.ELIGIBLE
        )

    def test_remote_americas(self):
        assert (
            classify_location("Americas", "remote", eligible_regions=REGIONS)
            is Eligibility.ELIGIBLE
        )

    def test_latin_america_spelled_out(self):
        assert (
            classify_location("Latin America - Remote", "remote", eligible_regions=REGIONS)
            is Eligibility.ELIGIBLE
        )


class TestIneligible:
    def test_onsite_abroad(self):
        # The gitlab-class case when the board is explicit: onsite in another
        # country can never be worked from Belo Horizonte.
        assert (
            classify_location("Bangalore, India", "onsite", home_city="Belo Horizonte")
            is Eligibility.INELIGIBLE
        )

    def test_hybrid_abroad(self):
        assert (
            classify_location("London, UK", "hybrid", home_city="Belo Horizonte")
            is Eligibility.INELIGIBLE
        )

    def test_onsite_brazil_outside_bh(self):
        # "Brasil onsite só conta se for Belo Horizonte."
        assert (
            classify_location("São Paulo, Brazil", "onsite", home_city="Belo Horizonte")
            is Eligibility.INELIGIBLE
        )

    def test_hybrid_brazil_outside_bh(self):
        assert (
            classify_location("Rio de Janeiro, Brazil", "hybrid", home_city="Belo Horizonte")
            is Eligibility.INELIGIBLE
        )


class TestAmbiguous:
    def test_no_location(self):
        assert classify_location(None, None) is Eligibility.AMBIGUOUS

    def test_empty_location(self):
        assert classify_location("", "remote") is Eligibility.AMBIGUOUS

    def test_bare_remote(self):
        # Recruitee's classic: "Remote job", no region anywhere.
        assert classify_location("Remote job", "remote") is Eligibility.AMBIGUOUS

    def test_foreign_country_but_remote(self):
        # The documented Colombia case: location says a country, the JD says
        # "work remotely from anywhere in LATAM" — only the LLM can read the JD,
        # so this must NOT be cut deterministically.
        assert classify_location("Colombia", "remote") is Eligibility.AMBIGUOUS

    def test_foreign_city_with_unknown_remote_type(self):
        # No explicit onsite signal: the JD may still say remote-worldwide.
        # The LLM decides — now seeing the location field.
        assert classify_location("Bangalore, India", None) is Eligibility.AMBIGUOUS


class TestHomeCity:
    def test_without_a_home_city_onsite_is_never_ruled_out(self):
        # A public user who has not said where they live: the LLM decides,
        # nothing is archived by location.
        assert classify_location("Bangalore, India", "onsite") is Eligibility.AMBIGUOUS

    def test_without_a_home_city_no_city_counts_as_home(self):
        assert classify_location("Belo Horizonte, MG", "hybrid") is Eligibility.AMBIGUOUS

    def test_the_home_city_is_whatever_the_profile_names(self):
        assert classify_location("Berlin, Germany", "onsite", home_city="berlin") is (
            Eligibility.ELIGIBLE
        )
        assert classify_location("Munich, Germany", "onsite", home_city="Berlin") is (
            Eligibility.INELIGIBLE
        )

    def test_the_home_city_is_matched_literally_not_as_a_pattern(self):
        assert classify_location("Stx Gallen", "onsite", home_city="St. Gallen") is (
            Eligibility.INELIGIBLE
        )

    def test_a_blank_home_city_is_no_home_city(self):
        assert classify_location("London, UK", "onsite", home_city="  ") is Eligibility.AMBIGUOUS


def test_home_city_among_several_locations_is_eligible():
    assert (
        classify_location("San Francisco; Belo Horizonte", "onsite", "Belo Horizonte")
        == Eligibility.ELIGIBLE
    )


def test_a_remote_option_among_several_places_is_not_cut_without_the_llm():
    assert classify_location("San Francisco; Remote (US)", "remote", "Belo Horizonte") == (
        Eligibility.AMBIGUOUS
    )


class TestEligibleRegionsFromTheProfile:
    def test_without_regions_no_location_is_eligible_by_region(self):
        # Unknown, not a default: a profile that names no region gets no shortcut.
        assert classify_location("Remote - Worldwide", "remote") is Eligibility.AMBIGUOUS
        assert classify_location("Brazil", "remote", eligible_regions=()) is Eligibility.AMBIGUOUS

    def test_the_regions_are_whatever_the_profile_names(self):
        assert classify_location("Remote (EMEA)", "remote", eligible_regions=("EMEA",)) is (
            Eligibility.ELIGIBLE
        )
        assert classify_location("Brazil", "remote", eligible_regions=("EMEA",)) is (
            Eligibility.AMBIGUOUS
        )

    def test_a_region_matches_a_whole_word_only(self):
        assert classify_location(
            "Remote (Pan-Americas)", "remote", eligible_regions=("Americas",)
        ) is (Eligibility.ELIGIBLE)
        assert classify_location(
            "Remote (Panamericas)", "remote", eligible_regions=("Americas",)
        ) is (Eligibility.AMBIGUOUS)

    def test_a_region_is_matched_literally_not_as_a_pattern(self):
        regions = ("U.S. (remote)", "C++")
        assert classify_location(
            "Anywhere in U.S. (remote)", "remote", eligible_regions=regions
        ) is (Eligibility.ELIGIBLE)
        assert classify_location("USxS (remote)", "remote", eligible_regions=regions) is (
            Eligibility.AMBIGUOUS
        )
        assert (
            classify_location("C++ shop", "remote", eligible_regions=regions)
            is Eligibility.ELIGIBLE
        )

    def test_a_region_never_overrides_the_onsite_cut(self):
        assert classify_location(
            "Rio de Janeiro, Brazil", "onsite", "Belo Horizonte", eligible_regions=REGIONS
        ) is (Eligibility.INELIGIBLE)


class TestEligibleRegionsFrom:
    def test_reads_the_list_and_strips_blanks(self):
        profile = {"criteria": {"eligible_regions": [" Brazil ", "", "  ", "LATAM"]}}
        assert eligible_regions_from(profile) == ("Brazil", "LATAM")

    def test_non_strings_are_ignored(self):
        assert eligible_regions_from({"criteria": {"eligible_regions": ["EMEA", 3, None]}}) == (
            "EMEA",
        )

    def test_absent_or_malformed_means_none(self):
        assert eligible_regions_from({}) == ()
        assert eligible_regions_from({"criteria": None}) == ()
        assert eligible_regions_from({"criteria": {}}) == ()
        assert eligible_regions_from({"criteria": {"eligible_regions": "Brazil"}}) == ()
