"""Deterministic guard for declaration/compliance questions.

Provenance: live incident 2026-08-21 (gympass #3416) — the composer picked the
public-body affiliation option on a conflict-of-interest form for a candidate
who never held such a position, in a field certifying the answers are true.
A signed false statement is a different failure class from a weak answer, so
these questions never reach the LLM: like references, salary and demographics,
they are operator territory ("answer this yourself" gap).

Detection is hybrid — a label match OR a marker in any option triggers the
guard. A false positive only costs a safe gap; a false negative risks a false
signed statement, so the patterns lean broad. Eligibility questions
(work authorization / sponsorship) deliberately match nothing here: they have
their own deterministic track in work_auth/field_map.
"""

import re
from collections.abc import Sequence

_LABEL = re.compile(
    r"conflict of interest|conflito de interesse"
    r"|\bdeclarations?\b|\bdeclare\b|\bdeclaro\b|declara[çc][ãa]o"
    r"|\bcertify\b|\bcertifico\b"
    r"|criminal record|antecedentes criminais"
    r"|\bcompliance\b",
    re.IGNORECASE,
)

_OPTION = re.compile(
    r"nothing to declare|nada a declarar"
    r"|public body|government entity|state-owned|political party"
    r"|[óo]rg[ãa]o p[úu]blico|partido pol[íi]tico"
    r"|\bi certify\b|\bcertifico\b"
    r"|conflict of interest|conflito de interesse",
    re.IGNORECASE,
)


def is_compliance_question(label: str, options: Sequence[str]) -> bool:
    """True when a form question is a declaration/compliance/conflict-of-interest
    question — recognized by its label or by the content of its options."""
    if _LABEL.search(label):
        return True
    return any(_OPTION.search(option) for option in options)
