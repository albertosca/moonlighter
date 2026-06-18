"""
Resolução país-dependente de campos de autorização de trabalho / visto /
sponsorship. Conservador por design: o país da vaga só é usado quando inferível
com confiança; do contrário, o campo vira o sentinel de revisão manual — nunca
um chute (responder errado sobre autorização é mentir).
"""

import re
from typing import Any

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
    ", ca",
    ", ny",
    ", wa",
    ", tx",
    "san francisco",
    "new york",
    "seattle",
    "austin",
    "boston",
)

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
    return None


def resolve_work_auth(field_label: str, country: str | None, config: dict[str, Any]) -> str | None:
    """
    Para campos de autorização/sponsorship retorna a resposta correta para o país,
    ou o sentinel de revisão quando o país é desconhecido. Retorna None se o campo
    não for de autorização (aí o LLM cuida).
    """
    wa = config.get("work_authorization", {}) or {}
    citizenship: str = (wa.get("citizenship_country") or "brazil").lower()
    yes: str = wa.get("authorized_answer", "Yes")
    no: str = wa.get("not_authorized_answer", "No")
    review: str = wa.get("needs_review_sentinel", "__NEEDS_REVIEW__")

    is_auth = bool(_AUTHORIZED_RE.search(field_label))
    is_sponsor = bool(_SPONSORSHIP_RE.search(field_label))
    if not (is_auth or is_sponsor):
        return None

    if country is None:
        return review

    authorized_here = country == citizenship
    if is_auth:
        return yes if authorized_here else no
    # sponsorship: precisa de patrocínio exatamente quando NÃO é autorizado lá.
    return no if authorized_here else yes
