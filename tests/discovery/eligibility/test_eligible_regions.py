"""Regions named by the profile: what classify_location does with them, and how they are read."""

from moonlighter.discovery.eligibility import Eligibility, classify_location, eligible_regions_from

from tests.discovery.eligibility.regions import REGIONS


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
