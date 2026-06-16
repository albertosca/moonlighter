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
    # Contato (EN)
    (r"^first\s+name", _first_name),
    (r"^last\s+name", _last_name),
    (r"preferred\s+(first\s+)?name", _first_name),
    (r"^(phone|telephone|mobile|cel)", lambda p: p.get("phone") or ""),
    (r"^e-?mail", lambda p: p.get("email") or ""),
    (r"linkedin", lambda p: p.get("linkedin") or ""),
    (r"^(website|portfolio|personal\s+site)", lambda p: p.get("website") or ""),
    # Contato (PT-BR) — "preferência" e "sobrenome" ANTES de "^nome" (ordem importa)
    (r"nome\s+de\s+prefer|prefer.*nome", _first_name),
    (r"^sobrenome", _last_name),
    (r"^nome", _first_name),
    (r"^(telefone|celular)", lambda p: p.get("phone") or ""),
    # Localização
    (r"location\s*\(?city", _city),
    (r"localiza|^cidade", _city),
    (r"^city$", _city),
    (r"^country$", lambda p: "Brazil"),
    (r"^pa[ií]s", lambda p: "Brasil"),
    # Autorização de trabalho / visto / sponsorship: NÃO ficam aqui — são tratados
    # de forma país-dependente em work_auth (resposta fixa seria mentira p/ vaga US).
    # Idiomas
    (r"english\s+level|english\s+proficiency|profici.*english", lambda p: "Fluent"),
    # Disponibilidade para escritório (Nubank pede 2-3x/semana)
    (r"work\s+from\s+the\s+office|office\s+at\s+least", lambda p: "Yes"),
    # Localização atual — ancorado no início p/ não casar frases de confirmação que
    # contêm "currently based" no meio (ex: "...require you to be currently based...").
    (r"^where\s+are\s+you\s+(currently\s+)?based|^current\s+location|^currently\s+based", _city),
]

_COMPILED: list[tuple[re.Pattern, object]] = [
    (re.compile(pattern, re.IGNORECASE), fn)
    for pattern, fn in _RULES
]


def pre_populate_answers(
    fields: list[str],
    profile: dict,
    config: dict | None = None,
    job_location: str | None = None,
    job_remote_type: str | None = None,
) -> dict[str, str]:
    """
    Retorna respostas conhecidas para os campos que batem com as regras estáticas
    (contato, localização, idioma). Campos de autorização de trabalho são tratados
    à parte, de forma país-dependente (ver work_auth). Campos sem match são
    ignorados (o LLM os preenche).
    """
    from candidatador.applicator.work_auth import infer_country, resolve_work_auth
    cfg = config or {}
    country = infer_country(job_location, job_remote_type)

    result: dict[str, str] = {}
    for field_label in fields:
        clean = field_label.strip().rstrip("*").strip()

        # 1) Autorização de trabalho (país-dependente, conservador)
        wa = resolve_work_auth(clean, country, cfg)
        if wa is not None:
            result[field_label] = wa
            continue

        # 2) Regras estáticas
        for pattern, fn in _COMPILED:
            if pattern.search(clean):
                value = fn(profile)
                if value:
                    result[field_label] = value
                break
    return result
