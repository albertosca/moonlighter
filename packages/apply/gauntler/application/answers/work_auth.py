"""
Resolução país-dependente de campos de autorização de trabalho / visto /
sponsorship. Conservador por design: o país da vaga só é usado quando inferível
com confiança; do contrário, o campo vira o sentinel de revisão manual — nunca
um chute (responder errado sobre autorização é mentir).
"""

import re
from typing import Any

from gauntler.core.config import NEEDS_REVIEW_SENTINEL

# Países/cidades que permitem inferência confiante. Lista curta de propósito:
# preferimos __NEEDS_REVIEW__ a um falso positivo.
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
    """Normaliza um nome de país (livre, qualquer locale) para a forma canônica
    usada na comparação. Desconhecido (nem BR nem US) → None (vira review)."""
    text = value.strip().lower()
    if text in ("brazil", "brasil", "br"):
        return "brazil"
    if text in ("united states", "usa", "us", "u.s.", "u.s.a", "united states of america"):
        return "united states"
    return None


# Detecta o tipo de campo. authorization e sponsorship são respondidos de forma
# OPOSTA conforme o país.
_AUTHORIZED_RE = re.compile(
    r"authorized.*work|work.*authoriz|legally.*work|work\s+permit|eligible.*work",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(
    r"sponsor|visa\s+support|require.*visa|visa.*support",
    re.IGNORECASE,
)


def infer_country(location: str | None, remote_type: str | None) -> str | None:
    """Retorna 'brazil', 'united states' ou None (quando não dá para afirmar)."""
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
    Para campos de autorização/sponsorship retorna a resposta correta para o país,
    ou o sentinel de revisão quando o país é desconhecido. Retorna None se o campo
    não for de autorização (aí o LLM cuida).
    """
    wa = config.get("work_authorization", {}) or {}
    # Normaliza pra forma canônica: aceita "Brasil"/"Brazil"/"BR" etc. sem depender
    # de locale exato. Vazio/ausente/desconhecido → None → review (conservador).
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
    # sponsorship: precisa de patrocínio exatamente quando NÃO é autorizado lá.
    return no if authorized_here else yes
