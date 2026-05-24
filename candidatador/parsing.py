import re


def _extract_json(raw: str) -> str:
    """
    Extrai JSON puro de uma resposta do LLM que pode conter markdown fences
    ou texto introdutório antes/depois do JSON.
    Tentativas em ordem: fence com label, fence sem label, objeto JSON nu.
    """
    raw = raw.strip()
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', raw)
    if m:
        return m.group(1).strip()
    m = re.search(r'(\{[\s\S]*\})', raw)
    if m:
        return m.group(1)
    return raw
