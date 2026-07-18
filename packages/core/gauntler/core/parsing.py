import json
import re
import secrets
from typing import Any


def extract_json(raw: str) -> str:
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


def parse_llm_json(raw: str) -> Any:
    """Extract a JSON payload from a raw LLM response (stripping prose/fences via
    extract_json) and parse it. Raises json.JSONDecodeError (a ValueError) on malformed input."""
    return json.loads(extract_json(raw))


def wrap_untrusted(label: str, text: str, *, cap: int | None = None) -> str:
    """Wrap external/untrusted text in an XML block with a random suffix
    (S-04). Two layers of defense against the text "escaping" the delimiter:

    1. Any literal occurrence of `<label...>`/`</label...>` already present in
       the text is stripped BEFORE wrapping — an attacker who reproduces the
       (predictable) label name cannot close the block early.
    2. The real tag uses a random per-call nonce (`label_XXXXXXXX`) — an
       attacker who has seen a tag from a prior interaction cannot replay it
       in this one.

    cap truncates the text BEFORE wrapping (applies to the whole block the
    caller assembles, not just one individual field); None = no truncation
    (for human-facing display text, not for an LLM prompt).
    """
    nonce = secrets.token_hex(4)
    tag = f"{label}_{nonce}"
    body = text if cap is None else text[:cap]
    body = re.sub(rf"</?{re.escape(label)}[^>]*>", "", body, flags=re.IGNORECASE)
    return f"<{tag}>\n{body}\n</{tag}>"
