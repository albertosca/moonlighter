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
from collections.abc import Callable
from typing import Any

_RuleFn = Callable[[dict[str, Any]], str | None]


def _first_name(profile: dict[str, Any]) -> str:
    return (profile.get("name") or "").split()[0]


def _last_name(profile: dict[str, Any]) -> str:
    parts = (profile.get("name") or "").split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


def _city(profile: dict[str, Any]) -> str:
    loc = profile.get("location") or ""
    return loc.split(",")[0].strip()


def _salary_expectation(profile: dict[str, Any]) -> str:
    target = (profile.get("preferences") or {}).get("salary_target_brl_monthly")
    return str(target) if target else ""


# Cada entrada: (padrão regex no label, callable(profile) -> str)
# Os padrões são case-insensitive e combinam substring.
_RULES: list[tuple[str, _RuleFn]] = [
    # Contato (EN)
    (r"^first\s+name", _first_name),
    (r"^last\s+name", _last_name),
    (r"preferred\s+(first\s+)?name", _first_name),
    (r"^(phone|telephone|mobile|cel)", lambda p: p.get("phone") or ""),
    (r"^e-?mail", lambda p: p.get("email") or ""),
    (r"linkedin", lambda p: p.get("linkedin") or ""),
    (r"^(website|portfolio|personal\s+site)", lambda p: p.get("website") or ""),
    # Compensation — filled statically so the salary figure never reaches the LLM (E2).
    # Not start-anchored: labels commonly lead with "Desired compensation" / "Expected salary".
    (
        r"salary|compensation|pretens|remunera|desired\s+pay|expected\s+(salary|pay)",
        _salary_expectation,
    ),
    # Contato (PT-BR) — "preferência" e "sobrenome" ANTES de "^nome" (ordem importa)
    (r"nome\s+de\s+prefer|prefer.*nome", _first_name),
    (r"^sobrenome", _last_name),
    (r"^nome", _first_name),
    (r"^(telefone|celular)", lambda p: p.get("phone") or ""),
    # Localização
    (r"location\s*\(?city", _city),
    (r"localiza|^cidade", _city),
    (r"^city$", _city),
    (r"^country$", lambda p: p.get("country_en") or None),
    (r"^pa[ií]s", lambda p: p.get("country_pt") or None),
    # Autorização de trabalho / visto / sponsorship: NÃO ficam aqui — são tratados
    # de forma país-dependente em work_auth (resposta fixa seria mentira p/ vaga US).
    # Idiomas
    (
        r"english\s+level|english\s+proficiency|profici.*english",
        lambda p: p.get("english_level") or None,
    ),
    # Disponibilidade para escritório — lê do profile; False → "No", ausente → None (LLM decide)
    (
        r"work\s+from\s+the\s+office|office\s+at\s+least",
        lambda p: ("Yes" if p["office_available"] else "No") if "office_available" in p else None,
    ),
    # Localização atual — ancorado no início p/ não casar frases de confirmação que
    # contêm "currently based" no meio (ex: "...require you to be currently based...").
    (r"^where\s+are\s+you\s+(currently\s+)?based|^current\s+location|^currently\s+based", _city),
]

_COMPILED: list[tuple[re.Pattern[str], _RuleFn]] = [
    (re.compile(pattern, re.IGNORECASE), fn) for pattern, fn in _RULES
]


def _static_answer(label: str, profile: dict[str, Any]) -> str | None:
    """Resposta da primeira regra estática que casa o label (vazia conta como sem match).

    Exceção: `_salary_expectation` sempre responde, mesmo vazia — o objetivo é que o
    campo de salário NUNCA caia pro LLM decidir (E2: a figura nunca deve chegar ao
    prompt), então mesmo sem preferência configurada o resultado é "" e não None.
    """
    for pattern, fn in _COMPILED:
        if pattern.search(label):
            if fn is _salary_expectation:
                return fn(profile)
            return fn(profile) or None
    return None


def pre_populate_answers(
    fields: list[str],
    profile: dict[str, Any],
    config: dict[str, Any] | None = None,
    job_location: str | None = None,
    job_remote_type: str | None = None,
) -> dict[str, str]:
    """
    Retorna respostas conhecidas para os campos que batem com as regras estáticas
    (contato, localização, idioma). Campos de autorização de trabalho são tratados
    à parte, de forma país-dependente (ver work_auth). Campos sem match são
    ignorados (o LLM os preenche).
    """
    from gauntler.application.answers.work_auth import infer_country, resolve_work_auth

    cfg = config or {}
    country = infer_country(job_location, job_remote_type)

    result: dict[str, str] = {}
    for field_label in fields:
        clean = field_label.strip().rstrip("*").strip()
        # Autorização de trabalho é país-dependente (conservador); o resto sai das
        # regras estáticas. Campos sem match ficam para o LLM responder.
        answer = resolve_work_auth(clean, country, cfg)
        if answer is None:
            answer = _static_answer(clean, profile)
        if answer is not None:
            result[field_label] = answer
    return result
