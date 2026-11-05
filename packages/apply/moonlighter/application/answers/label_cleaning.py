"""Strips the decoration a form hangs on a label, so an anchored rule can match it."""

import re

# A line that carries no question: a required marker, or a dial code.
_DECORATION = re.compile(r"[*†‡]+|\+\d{1,4}")
# What trails a label without being part of it: a marker ("*", "(required)",
# "(obrigatório)", "(optional)", "(opcional)") or a colon. "Name:" and
# "Name (required)" went unmatched while "Name *" matched (2026-09-29 review).
_TRAILING_MARKER = re.compile(
    r"\s*(?:[*†‡:]+|\((?:required|obrigat[óo]rio|optional|opcional)\))\s*$", re.IGNORECASE
)


def clean_label(field_label: str) -> str:
    r"""The label a rule should match, with the form's decoration removed.

    Every static rule is ^-anchored, and forms decorate labels in ways that break
    that anchor. Workable puts the required marker on a line of its OWN, BEFORE
    the text ("*\nFirst name"), and appends the dial code after it
    ("*\nPhone\n+55"). Observed on a live posting 2026-08-04: nothing matched,
    so name, phone and the tracking email were all left for the LLM to invent.

    Only lines that are pure decoration are dropped — a marker, or a dial code.
    A label whose first line is real text keeps every line, since collapsing it
    would let unrelated rules match.
    """
    lines = [line.strip() for line in field_label.strip().splitlines()]
    kept = [line for line in lines if line and not _DECORATION.fullmatch(line)]
    label = kept[0] if kept else ""
    previous = None
    while previous != label:
        previous = label
        label = _TRAILING_MARKER.sub("", label)
    return label
