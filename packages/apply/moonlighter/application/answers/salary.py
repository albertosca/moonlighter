"""The salary rule: which labels it claims, and what it answers in the profile's units."""

import re
from typing import Any

from moonlighter.application.answers.needs_review import NEEDS_REVIEW_SENTINEL

# Compensation — filled statically so the salary figure never reaches the LLM (E2).
# The label must be a short *value* question: an optional lead (desired/expected/…/minimum/base/total),
# the keyword, an optional whitelisted value-qualifier (expectation/range/salari…/…),
# then end-of-label (allowing a SHORT trailing parenthetical/colon). Anchoring on both
# ends with a qualifier whitelist is what rejects essay labels that merely START with
# the keyword — "Salary history — describe…" and "Compensation philosophy: …" continue
# into a non-whitelisted word, so they never reach `$` and fall through to the LLM.
# The parenthetical is bounded to 15 chars: it exists for short currency/period notes
# ("(BRL)", "(monthly)"), and an unbounded `[^)]*` reopened the essay over-match by
# letting "Salary (please describe your history…)" slip through. Three earlier versions
# failed here: unanchored over-matched mid-sentence mentions; start-only-anchored still
# swallowed start-anchored essays; and an unbounded parenthetical smuggled essays in
# parens — all silently replacing the field with a bare number. Also supports bare PT-BR
# keywords (Salário, Faixa salarial) to match form labels in Portuguese without a lead word.
# A fourth widening (2026-08-12) adds an optional interrogative lead ("What is your", "What's",
# "Qual (é) sua") and allows the `?` on either side of the parenthetical, matching the live
# Holepunch label "What is your expected salary? (annual USD)". It holds because the lead is a
# closed alternation ending in "your"/"sua", so essays that continue into non-whitelisted words
# ("What is your view on salary transparency?") still never reach `$`.
# See tests/application/answers/salary/ for every regression case.
SALARY_LABEL_PATTERN = (
    r"^(?:(?:what\s+is|what[’']s|what\s+are)\s+your\s+|qual\s+(?:é\s+)?(?:a\s+)?sua\s+)?"
    r"(?:(?:desired|expected|current|target|minimum|base|total)\s+)?"
    r"(?:salary|compensation|pay|pretens\w*|remunera\w*|sal[aá]rio|faixa\s+salarial)"
    r"(?:\s+(?:expectations?|requirements?|range|salari\w*|pretendid\w*|desejad\w*"
    r"|mensa(?:l|is)|monthly|anual|annual|target|desired|expected))*"
    r"\s*\??\s*(?:\([^)]{0,15}\))?\s*\??\s*:?\s*$"
)

# The stored figure is BRL per month — the preference key says so. A label that
# asks for anything else (annual USD is the common case on remote-worldwide
# postings) would receive that number unconverted: "35000" read as $35,000/year
# instead of R$35.000/month is the wrong currency AND ~2.4x under the intended
# figure. Observed on a live Recruitee posting (2026-08-03), which escaped only because
# its label happens to start with "What is your", which the anchor then rejected.
_FOREIGN_CURRENCY = re.compile(
    r"\b(usd|us\$|u\$|dollars?|eur|euros?|gbp|pounds?)\b|[€£]", re.IGNORECASE
)
_OTHER_PERIOD = re.compile(
    r"\b(annual(ly)?|year(ly)?|per\s+year|p\.?a\.?|anual|ano)\b", re.IGNORECASE
)


def salary_expectation(profile: dict[str, Any], label: str = "") -> str:
    """The configured salary target, or NEEDS_REVIEW when the units disagree.

    Never returns None: the salary field must not fall through to the LLM (E2 —
    the figure must never reach the prompt). The sentinel keeps that property
    while refusing to state a number in units nobody verified — the composer turns
    it into a gap, so nothing is typed, and the service already reports sentinel
    fields as pending for the human. Converting instead would need an FX rate
    and would bake an unstated assumption into a salary negotiation.
    """
    target = (profile.get("preferences") or {}).get("salary_target_brl_monthly")
    if target is None:
        return ""
    if _FOREIGN_CURRENCY.search(label) or _OTHER_PERIOD.search(label):
        return NEEDS_REVIEW_SENTINEL
    # Currency + dot-separated thousands + explicit period, the format ATS labels
    # themselves exemplify ("MXN 9.000"). A bare "35000" left currency and period
    # to the reader's guess — observed live on the Nubank form (2026-08-13),
    # whose label asked for "Currency + Monthly Salary" outright.
    return f"BRL {target:,}/month".replace(",", ".")
