"""The static rule ladder: which profile value answers which label, first match winning."""

import re
from collections.abc import Callable
from typing import Any

from moonlighter.application.answers.rules.salary import SALARY_LABEL_PATTERN, salary_expectation

_RuleFn = Callable[[dict[str, Any]], str | None]


def _first_name(profile: dict[str, Any]) -> str:
    return (profile.get("name") or "").split()[0]


def _last_name(profile: dict[str, Any]) -> str:
    parts = (profile.get("name") or "").split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


def _city(profile: dict[str, Any]) -> str:
    loc = profile.get("location") or ""
    return loc.split(",")[0].strip()


# Each entry: (regex pattern on the label, callable(profile) -> str)
# Patterns are case-insensitive and match by substring.
_RULES: list[tuple[str, _RuleFn]] = [
    # Contact, English labels
    # "Full name" as a single field is the norm outside the Greenhouse/Lever
    # first+last convention; it must precede the first/last rules only in intent,
    # not in matching (the anchors are disjoint), but it must precede "^nome" in
    # the PT-BR block below, which would otherwise reduce it to a first name.
    (r"^(your\s+)?full\s+name", lambda profile: profile.get("name") or ""),
    # A bare "Name" (Ashby's application page) is the full name. Anchored at both
    # ends: "Name of your current employer" is a different question. It went to
    # the LLM, which answered "I DON'T KNOW" (ElevenLabs #6675, 2026-09-25).
    (r"^(your\s+)?name$", lambda profile: profile.get("name") or ""),
    (r"^first\s+name", _first_name),
    (r"^last\s+name", _last_name),
    (r"preferred\s+(first\s+)?name", _first_name),
    (r"^(phone|telephone|mobile|cel)", lambda profile: profile.get("phone") or ""),
    (r"^e-?mail", lambda profile: profile.get("email") or ""),
    (r"linkedin", lambda profile: profile.get("linkedin") or ""),
    # A "Github" field became a gap on the live Resend form (2026-08-20):
    # linkedin and website had rules, github never did.
    (r"github", lambda profile: profile.get("github") or ""),
    (r"^(website|portfolio|personal\s+site)", lambda profile: profile.get("website") or ""),
    # Compensation — the salary rule, its anchors and its history live in salary.py.
    (SALARY_LABEL_PATTERN, salary_expectation),
    # Contact, PT-BR labels — "preferência" and "sobrenome" BEFORE "^nome" (order matters)
    (r"nome\s+de\s+prefer|prefer.*nome", _first_name),
    (r"^sobrenome", _last_name),
    (r"^nome\s+completo", lambda profile: profile.get("name") or ""),
    (r"^nome", _first_name),
    (r"^(telefone|celular)", lambda profile: profile.get("phone") or ""),
    # Location
    (r"location\s*\(?city", _city),
    (r"localiza|^cidade", _city),
    (r"^city$", _city),
    (r"^country$", lambda profile: profile.get("country_en") or None),
    (r"^pa[ií]s", lambda profile: profile.get("country_pt") or None),
    (r"^address$", lambda profile: profile.get("location") or None),
    # Work authorization / visa / sponsorship: NOT handled here — dealt with in a
    # country-dependent way in work_auth (a fixed answer would be a lie for a US job).
    # Languages
    (
        r"english\s+level|english\s+proficiency|profici.*english",
        lambda profile: profile.get("english_level") or None,
    ),
    # Office availability — reads from the profile; False → "No", absent → None (LLM decides)
    (
        r"work\s+from\s+the\s+office|office\s+at\s+least",
        lambda profile: (
            ("Yes" if profile["office_available"] else "No")
            if "office_available" in profile
            else None
        ),
    ),
    # EEO/demographic self-identification is NOT here — see `demographic_answer` and
    # `_DEMOGRAPHIC_RULES` in demographics.py. A demographic label never reaches this ladder,
    # because composer's is_sensitive_label guard intercepts it first.
    # Current location — anchored at the start so it doesn't match confirmation
    # phrases containing "currently based" mid-sentence (e.g. "...require you to be
    # currently based...").
    (r"^where\s+are\s+you\s+(currently\s+)?based|^current\s+location|^currently\s+based", _city),
]

_COMPILED: list[tuple[re.Pattern[str], _RuleFn]] = [
    (re.compile(pattern, re.IGNORECASE), rule) for pattern, rule in _RULES
]


def static_answer(label: str, profile: dict[str, Any]) -> str | None:
    """Answer from the first static rule matching the label (empty counts as no match).

    Exception: `salary_expectation` always answers, even if empty — the goal is that
    the salary field NEVER falls through to the LLM to decide (E2: the figure must
    never reach the prompt), so even without a configured preference the result is ""
    rather than None.
    """
    for pattern, rule in _COMPILED:
        if pattern.search(label):
            if rule is salary_expectation:
                # Called directly, not through `rule`: this is the one rule that
                # needs the label, to check the currency/period it asks for.
                return salary_expectation(profile, label)
            return rule(profile) or None
    return None
