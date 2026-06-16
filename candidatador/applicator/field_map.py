"""
Mapeamento de campos de formulário ATS para dados do perfil do candidato.

Evita depender do LLM para campos de contato e respostas padronizadas que
o LLM não consegue inferir corretamente (ex: phone vazio).

Uso: `pre_populate_answers(fields, profile)` retorna um dict de respostas
conhecidas, que é depois mesclado com as respostas geradas pelo LLM
(o LLM pode sobrescrever se tiver resposta melhor, mas os campos de
contato ficam garantidos).
"""

import re


def _first_name(profile: dict) -> str:
    return (profile.get("name") or "").split()[0]


def _last_name(profile: dict) -> str:
    parts = (profile.get("name") or "").split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


def _city(profile: dict) -> str:
    loc = profile.get("location") or ""
    return loc.split(",")[0].strip()


# Cada entrada: (padrão regex no label, callable(profile) -> str)
# Os padrões são case-insensitive e combinam substring.
_RULES: list[tuple[str, object]] = [
    # Contato
    (r"^first\s+name", _first_name),
    (r"^last\s+name", _last_name),
    (r"preferred\s+(first\s+)?name", _first_name),
    (r"^(phone|telephone|mobile|cel)", lambda p: p.get("phone") or ""),
    (r"^email", lambda p: p.get("email") or ""),
    (r"linkedin", lambda p: p.get("linkedin") or ""),
    (r"^(website|portfolio|personal\s+site)", lambda p: p.get("website") or ""),
    # Localização
    (r"location\s*\(?city", _city),
    (r"^city$", _city),
    (r"^country$", lambda p: "Brazil"),
    # Autorização de trabalho / visto — sempre negativo pra BR
    (r"visa\s+support|require.*visa|visa.*sponsor", lambda p: "No"),
    (r"authorized.*work|work.*authorized|work\s+permit|eligible.*work", lambda p: "Yes"),
    (r"require\s+sponsorship|need.*sponsorship|sponsorship.*required", lambda p: "No"),
    # Idiomas
    (r"english\s+level|english\s+proficiency|profici.*english", lambda p: "Fluent"),
    # Disponibilidade para escritório (Nubank pede 2-3x/semana)
    (r"work\s+from\s+the\s+office|office\s+at\s+least", lambda p: "Yes"),
    # Localização atual
    (r"currently\s+based|where\s+are\s+you\s+based|current\s+location", _city),
]

_COMPILED: list[tuple[re.Pattern, object]] = [
    (re.compile(pattern, re.IGNORECASE), fn)
    for pattern, fn in _RULES
]


def pre_populate_answers(fields: list[str], profile: dict) -> dict[str, str]:
    """
    Retorna respostas conhecidas para os campos que batem com as regras.
    Campos sem match são ignorados (o LLM os preenche).
    """
    result: dict[str, str] = {}
    for field_label in fields:
        clean = field_label.strip().rstrip("*").strip()
        for pattern, fn in _COMPILED:
            if pattern.search(clean):
                value = fn(profile)
                if value:
                    result[field_label] = value
                break
    return result
