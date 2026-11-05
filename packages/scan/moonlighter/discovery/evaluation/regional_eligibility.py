"""The prompt section that tells the model how to judge where the candidate can work from."""

from typing import Any

_REGIONAL_ELIGIBILITY = """## Regional eligibility
When a hard filter concerns where the candidate can work from, judge it against the posting's
Location and Remote type lines as well as the description. When a Location line names a country,
region or city that neither it nor the description opens to the candidate, that is a triggered hard
filter — do not reinterpret the stated location as an inconsistency to discount; score it ≤ 2.0 and
record the reason in `caveats`. With no such hard filter, location alone never caps the score.
{precedence}
When the posting requires fluency in a language the candidate's profile does not list under
`languages` (e.g. "fluent Italian required"), that is a triggered hard filter: score it ≤ 2.0 and
record it in `caveats`, prefixed "language:". A language listed as a plus or nice-to-have is not.
"""

# criteria.location_precedence in profile.yaml: which wins when a description
# carries both a company-wide remote claim and a posting-specific location. The
# default is "specific": ElevenLabs Netherlands/Italy (2026-09-28) scored 6.3-8.0
# because a boilerplate "can be executed globally" beat "from anywhere in Italy,
# Italian required" further down.
_PRECEDENCE = {
    "specific": (
        'When the description has both a generic company-wide remote claim ("this role is remote and\n'
        'can be executed globally") and a posting-specific location paragraph ("from anywhere in\n'
        'Italy"), the posting-specific location paragraph wins: judge eligibility by it.'
    ),
    "generic": (
        'When the description has both a generic company-wide remote claim ("this role is remote and\n'
        'can be executed globally") and a posting-specific location paragraph ("from anywhere in\n'
        'Italy"), the generic company-wide remote claim wins, as the candidate chose: treat the\n'
        "posting as open unless its Location line itself excludes the candidate."
    ),
}

LOCATION_PRECEDENCES = tuple(_PRECEDENCE)


def regional_eligibility_section(profile: dict[str, Any]) -> str:
    criteria = profile.get("criteria") or {}
    choice = criteria.get("location_precedence") if isinstance(criteria, dict) else None
    precedence = _PRECEDENCE.get(str(choice), _PRECEDENCE["specific"])
    return _REGIONAL_ELIGIBILITY.format(precedence=precedence)
