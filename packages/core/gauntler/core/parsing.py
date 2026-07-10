import re
import secrets


def _extract_json(raw: str) -> str:
    """
    Extrai JSON puro de uma resposta do LLM que pode conter markdown fences
    ou texto introdutório antes/depois do JSON.
    Tentativas em ordem: fence com label, fence sem label, objeto JSON nu.
    """
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", raw)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\{[\s\S]*\})", raw)
    if m:
        return m.group(1)
    return raw


def wrap_untrusted(label: str, text: str, *, cap: int | None = None) -> str:
    """Envolve texto externo/não-confiável num bloco XML com sufixo aleatório
    (S-04). Duas camadas de defesa contra o texto "escapar" do delimitador:

    1. Toda ocorrência literal de `<label...>`/`</label...>` já existente no
       texto é removida ANTES de envolver — um atacante que reproduza o nome
       do label (previsível) não consegue fechar o bloco cedo.
    2. A tag real usa um nonce aleatório por chamada (`label_XXXXXXXX`) — um
       atacante que tenha visto uma tag de uma interação anterior não pode
       replicá-la nesta.

    cap trunca o texto ANTES de envolver (aplica-se ao bloco inteiro que o
    chamador montar, não só a um campo individual); None = sem truncamento
    (uso para texto de exibição humana, não para prompt de LLM).
    """
    nonce = secrets.token_hex(4)
    tag = f"{label}_{nonce}"
    body = text if cap is None else text[:cap]
    body = re.sub(rf"</?{re.escape(label)}[^>]*>", "", body, flags=re.IGNORECASE)
    return f"<{tag}>\n{body}\n</{tag}>"
