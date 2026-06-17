"""Alias de rastreamento +ref no campo de email do formulário ATS.

A empresa responde em candidaturas+<ref>@gmail.com (conta monitorada),
o que permite ao email_monitor casar a resposta com a candidatura pelo ref.
"""


def build_email_alias(address: str, ref: str) -> str:
    """'candidaturas@gmail.com' + 'x7k2mp' → 'candidaturas+x7k2mp@gmail.com'"""
    local, _, domain = address.partition("@")
    return f"{local}+{ref}@{domain}"


def inject_email_alias(answers: dict, alias: str) -> bool:
    """
    Sobrescreve o campo de email do formulário com o alias +ref de rastreamento.
    Procura qualquer label que contenha 'email' ignorando hífen/espaço — assim
    casa tanto 'Email' quanto 'E-mail' (PT). Se não houver, adiciona uma chave
    'Email' como fallback (label mais comum nos ATS).
    Retorna True se algum campo existente foi sobrescrito.
    """
    injected = False
    for key in list(answers.keys()):
        normalized = key.lower().replace("-", "").replace(" ", "")
        if "email" in normalized:
            answers[key] = alias
            injected = True
    if not injected:
        answers["Email"] = alias
    return injected
