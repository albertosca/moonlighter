"""Catch model prose addressed to the tool's operator instead of the employer.

Shared by the answer composer and the tailored CV, so it imports nothing: a
guard both sides lean on must not pull either side into the other's graph.
"""

# Markers of prose addressed to the tool's operator instead of the employer.
# Provenance: two live incidents — a references answer (2026-08-04) and an
# address answer (2026-08-05) written ABOUT the candidate in the third person,
# instructing whoever drives the tool. A prompt-only fix failed twice; this
# guard is deterministic. False positives are acceptable by construction: the
# failure direction is a human answering one more question by hand.
_OPERATOR_MARKERS = (
    "the candidate",
    "the applicant",
    "cannot attach",
    "unable to attach",
    "please supply",
    "please provide",
    "please upload",
    "material provided",
    "before submitting",
)


def find_operator_marker(answer: str) -> str | None:
    """The first operator-directed marker found in the answer, or None."""
    lowered = answer.lower()
    for marker in _OPERATOR_MARKERS:
        if marker in lowered:
            return marker
    return None
