"""Answers EEO self-identification labels from the demographics the operator configured."""

import re
from typing import Any

from moonlighter.application.answers.matching.label_cleaning import clean_label

# EEO/demographic self-identification, from the `demographics:` block the operator
# configures in profile.yaml. Kept OUT of static_rules.py's `_RULES` on purpose: a
# demographic label is intercepted by composer's is_sensitive_label guard before
# `known` is consulted, so a rule there would be unreachable — and putting the
# carve-out in the general ladder is exactly what broke on 2026-09-11, when letting
# `known` outrank the guard handed the bypass to every other rule too (a
# "references ... LinkedIn" label came back answered with the LinkedIn URL).
# `demographic_answer` is called only from inside that guard, for choice questions
# only.
#
# Anchored at BOTH ends, and matched against a closed set of real EEO phrasings —
# not just the leading word. Two measured failures got us here:
#   unanchored  (2026-09-11): `\brace\b` matched "debug a race condition", so an
#                             engineering essay came back answered "White";
#   start-only  (2026-09-13): `^race\b` matched "Race conditions: how do you debug
#                             them?", and `^veteran\b` matched "Veteran of the
#                             startup wars?" — same defect, one shape further in.
# This is the same lesson the salary rule in salary.py already learned across three failed
# widenings: a short *value* question anchors on both ends; anything that continues
# into other words is a different question and must fall through.
#
# Each entry: (both-ends-anchored pattern, demographics key). The label is
# normalised first (see `_normalise_eeo_label`): lowercased, decoration and a short
# trailing parenthetical removed.
_DEMOGRAPHIC_RULES: tuple[tuple[str, str], ...] = (
    (
        (
            r"^(are\s+you\s+)?hispanic(\s*(or|/)\s*latino)?$"
            r"|^ethnicity\s*[:/]\s*hispanic(\s*(or|/)\s*latino)?$"
        ),
        "hispanic_latino",
    ),
    (r"^gender(\s+identity)?$|^voluntary\s+self[-\s]?identification\s+of\s+gender$", "gender"),
    (
        # Bare `^ethnicity$` deliberately absent: on a US EEO form that usually means
        # the Hispanic/Latino question, not race, so serving the race value there is
        # a guess. The rule existed and was unreachable until "Ethnicity" became a
        # sensitive label (2026-09-14); it was deleted rather than switched on.
        # `Race/Ethnicity` — one combined question — stays unambiguous.
        (
            r"^race$|^race\s*(/|&|and|or)\s*ethnicity$"
            r"|^voluntary\s+self[-\s]?identification\s+of\s+race$"
        ),
        "race",
    ),
    (
        (
            r"^(protected\s+)?veteran(\s+status)?$|^are\s+you\s+a\s+(protected\s+)?veteran$"
            r"|^voluntary\s+self[-\s]?identification\s+of\s+(protected\s+)?veteran(\s+status)?$"
        ),
        "veteran_status",
    ),
    (
        (
            r"^disability(\s+status)?$|^do\s+you\s+have\s+a\s+disability$"
            r"|^voluntary\s+self[-\s]?identification\s+of\s+disability$"
        ),
        "disability_status",
    ),
)

# Decoration a real form hangs off an otherwise-exact EEO label: a required marker,
# a trailing colon/question mark, or one of a CLOSED SET of benign notes.
#
# The note list is an allowlist, not a length bound. A blanket "strip any short
# parenthetical" rule was tried first and cut both ways in the same change: it
# swallowed "(insurance)" and "(of which war?)" — turning "Disability (insurance)"
# into an exact EEO match answered "No" — while its 20-character bound missed
# "(select all that apply)" by one character, refusing a real multi-select race
# question. Naming the notes we accept closes both ends at once.
_EEO_NOTES = (
    r"optional",
    r"required",
    r"not\s+required",
    r"select\s+all\s+that\s+apply",
    r"choose\s+all\s+that\s+apply",
    r"voluntary",
    r"us\s+only",
    r"cc[-\s]?305",
    r"eeo(c)?",
)
_EEO_DECORATION = re.compile(
    r"\s*[(\[]\s*(" + "|".join(_EEO_NOTES) + r")\s*[)\]]\s*$|[\s*:?—–-]+$",
    re.IGNORECASE,
)

_DEMOGRAPHIC_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), key) for pattern, key in _DEMOGRAPHIC_RULES
)


def _demographic(profile: dict[str, Any], key: str) -> str | None:
    """The configured value for one demographics key, or None when unset.

    Coerces to str deliberately: `profile.yaml` is read with `yaml.safe_load`
    (YAML 1.1), where an unquoted `No`/`Yes` parses as a bool. Left raw, a `False`
    read as unconfigured (silently losing a configured answer) and a `True` reached
    `known` as a non-str, crashing the whole sheet with
    `AttributeError: 'bool' object has no attribute 'strip'`.
    """
    value = (profile.get("demographics") or {}).get(key)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise_eeo_label(field_label: str) -> str:
    """The label an EEO pattern should match, with a form's decoration removed.

    Applied repeatedly, because a real label stacks decoration: "Gender (optional):"
    sheds the parenthetical and then the colon.
    """
    text = clean_label(field_label).strip().lower()
    while True:
        stripped = _EEO_DECORATION.sub("", text).strip()
        if stripped == text:
            return text
        text = stripped


def demographic_answer(field_label: str, profile: dict[str, Any]) -> str | None:
    """The operator's own configured answer for an EEO label, or None.

    Called only from composer's is_sensitive_label guard, so it never competes
    with the general `_RULES` ladder — the point is that a value the operator
    wrote in profile.yaml is his answer, not a model guess, while everything
    else sensitive stays a manual gap.
    """
    clean = _normalise_eeo_label(field_label)
    for pattern, key in _DEMOGRAPHIC_COMPILED:
        if pattern.search(clean):
            return _demographic(profile, key)
    return None
