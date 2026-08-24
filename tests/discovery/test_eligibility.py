"""Deterministic regional-eligibility classification from structured fields.

Provenance: live incident 2026-08-20/21 (job 7733 and the gitlab cluster) —
the eligibility hard filter lived only in the evaluator prompt, which sees the
DESCRIPTION; on boards like GitLab the region lives in the posting's location
field ("Bangalore, India"), which the LLM never saw. 32/32 gitlab jobs and
~2/3 of the whole queue were false positives, all cut by hand.

Alberto's rule: eligible = remote with an explicit eligible region
(BR/LATAM/Americas/global/worldwide) OR onsite in Belo Horizonte.
"""

from moonlighter.discovery.eligibility import Eligibility, classify_location


class TestEligible:
    def test_belo_horizonte_onsite(self):
        assert classify_location("Belo Horizonte, Brazil", "onsite") is Eligibility.ELIGIBLE

    def test_remote_worldwide(self):
        assert classify_location("Remote - Worldwide", "remote") is Eligibility.ELIGIBLE

    def test_remote_latam(self):
        assert classify_location("Remote (LATAM)", "remote") is Eligibility.ELIGIBLE

    def test_remote_brazil(self):
        assert classify_location("Brazil", "remote") is Eligibility.ELIGIBLE

    def test_remote_americas(self):
        assert classify_location("Americas", "remote") is Eligibility.ELIGIBLE

    def test_latin_america_spelled_out(self):
        assert classify_location("Latin America - Remote", "remote") is Eligibility.ELIGIBLE


class TestIneligible:
    def test_onsite_abroad(self):
        # The gitlab-class case when the board is explicit: onsite in another
        # country can never be worked from Belo Horizonte.
        assert classify_location("Bangalore, India", "onsite") is Eligibility.INELIGIBLE

    def test_hybrid_abroad(self):
        assert classify_location("London, UK", "hybrid") is Eligibility.INELIGIBLE

    def test_onsite_brazil_outside_bh(self):
        # "Brasil onsite só conta se for Belo Horizonte."
        assert classify_location("São Paulo, Brazil", "onsite") is Eligibility.INELIGIBLE

    def test_hybrid_brazil_outside_bh(self):
        assert classify_location("Rio de Janeiro, Brazil", "hybrid") is Eligibility.INELIGIBLE


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
