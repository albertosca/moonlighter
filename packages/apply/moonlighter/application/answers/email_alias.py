"""+ref tracking alias for the email field on the ATS form.

The company replies to candidaturas+<ref>@gmail.com (monitored account),
which lets email_monitor match the reply to the application by the ref.
"""


def build_email_alias(address: str, ref: str) -> str:
    """'candidaturas@gmail.com' + 'x7k2mp' → 'candidaturas+x7k2mp@gmail.com'"""
    local, _, domain = address.partition("@")
    return f"{local}+{ref}@{domain}"


def inject_email_alias(answers: dict[str, str], alias: str) -> bool:
    """
    Overwrites the form's email field with the +ref tracking alias.
    Looks for any label containing 'email' ignoring hyphen/space — this
    matches both 'Email' and 'E-mail' (PT). If none exists, adds an
    'Email' key as a fallback (the most common label across ATS).
    Returns True if some existing field was overwritten.
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
