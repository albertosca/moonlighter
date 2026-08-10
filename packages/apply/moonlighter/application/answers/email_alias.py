"""+ref tracking alias for the email field on the ATS form.

The company replies to candidaturas+<ref>@gmail.com (monitored account),
which lets email_monitor match the reply to the application by the ref.
"""

import secrets

# No uppercase: a mail provider may lowercase the local part of an address, and a ref
# that changes in transit cannot be matched back. No l/o/0/1 either, so a ref stays
# readable when someone reads it off a screen.
_REF_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
_REF_LENGTH = 8


def new_email_ref() -> str:
    """A tracking ref that survives the trip through a mail provider unchanged."""
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(_REF_LENGTH))


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
