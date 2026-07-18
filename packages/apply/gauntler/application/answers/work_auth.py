"""
Country-dependent resolution of work-authorization / visa / sponsorship
fields. Conservative by design: the job's country is only used when it can
be confidently inferred; otherwise the field becomes the manual-review
sentinel — never a guess (answering wrong about authorization is lying).
"""

import re
from typing import Any

from gauntler.core.config import NEEDS_REVIEW_SENTINEL

# Countries/cities that allow confident inference. Deliberately short list:
# we prefer __NEEDS_REVIEW__ over a false positive.
_BRAZIL_MARKERS = (
    "brazil",
    "brasil",
    "são paulo",
    "sao paulo",
    "rio de janeiro",
    "belo horizonte",
    "porto alegre",
    "curitiba",
    "recife",
    "florianópolis",
    "florianopolis",
    "campinas",
)
_US_MARKERS = (
    "united states",
    "usa",
    "u.s.",
    "u.s.a",
    "san francisco",
    "new york",
    "seattle",
    "austin",
    "boston",
)
# State codes (", CA"/", NY"/...) need a word-boundary: as a plain substring,
# ", ca" would match "Toronto, Ca-nada" and misclassify a Canadian posting as US.
# "CA" itself is ambiguous even with the word-boundary fix: it is both the
# US-state code (California) and the ISO 3166 alpha-2 country code for Canada.
# Rather than try to disambiguate by enumerating Canadian cities/provinces,
# infer_country below treats ANY location whose matched state code is "CA" as
# unresolvable (returns None, which downstream becomes NEEDS_REVIEW_SENTINEL)
# — never a guessed country. This is conservative by design: a legitimate
# California posting also lands in manual review, an accepted tradeoff over
# risking a wrong work-authorization answer.
_US_STATE_RE = re.compile(r",\s*(ca|ny|wa|tx)\b")


def _canonical_country(value: str) -> str | None:
    """Normalizes a country name (free-form, any locale) to the canonical form
    used for comparison. Unknown (neither BR nor US) → None (becomes review)."""
    text = value.strip().lower()
    if text in ("brazil", "brasil", "br"):
        return "brazil"
    if text in ("united states", "usa", "us", "u.s.", "u.s.a", "united states of america"):
        return "united states"
    return None


# Detects the field type. authorization and sponsorship are answered in
# OPPOSITE ways depending on the country.
_AUTHORIZED_RE = re.compile(
    r"authorized.*work|work.*authoriz|legally.*work|work\s+permit|eligible.*work",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(
    r"sponsor|visa\s+support|require.*visa|visa.*support",
    re.IGNORECASE,
)


def infer_country(location: str | None, remote_type: str | None) -> str | None:
    """Returns 'brazil', 'united states', or None (when it can't be asserted)."""
    text = (location or "").lower()
    if any(m in text for m in _BRAZIL_MARKERS):
        return "brazil"
    if any(m in text for m in _US_MARKERS):
        return "united states"
    state_match = _US_STATE_RE.search(text)
    if state_match:
        # ", CA" is ambiguous (California vs. Canada) — never guess.
        return None if state_match.group(1) == "ca" else "united states"
    return None


def resolve_work_auth(field_label: str, country: str | None, config: dict[str, Any]) -> str | None:
    """
    For authorization/sponsorship fields returns the correct answer for the country,
    or the review sentinel when the country is unknown. Returns None if the field
    is not authorization-related (then the LLM handles it).
    """
    wa = config.get("work_authorization", {}) or {}
    # Normalizes to the canonical form: accepts "Brasil"/"Brazil"/"BR" etc. without
    # depending on the exact locale. Empty/missing/unknown → None → review (conservative).
    citizenship = _canonical_country(wa.get("citizenship_country") or "")
    yes: str = wa.get("authorized_answer", "Yes")
    no: str = wa.get("not_authorized_answer", "No")
    review: str = NEEDS_REVIEW_SENTINEL

    is_auth = bool(_AUTHORIZED_RE.search(field_label))
    is_sponsor = bool(_SPONSORSHIP_RE.search(field_label))
    if not (is_auth or is_sponsor):
        return None

    if not citizenship or country is None:
        return review

    authorized_here = country == citizenship
    if is_auth:
        return yes if authorized_here else no
    # sponsorship: needs sponsorship exactly when NOT authorized there.
    return no if authorized_here else yes
