"""+ref tracking alias for the email field on the ATS form.

The company replies to <account>+<ref>@gmail.com (the configured tracking account),
which lets email_monitor match the reply to the application by the ref.
"""

import re
import secrets

# No uppercase: a mail provider may lowercase the local part of an address, and a ref
# that changes in transit cannot be matched back. No l/o/0/1 either, so a ref stays
# readable when someone reads it off a screen.
_REF_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
_REF_LENGTH = 8

# Anchored like field_map's own email rule (`^e-?mail`), so the two definitions of
# "the email field" cannot drift apart: the alias replaces exactly the labels the
# field map would have filled with the profile email. The \b keeps "Emailing
# preferences" out while letting "E-mail*" and "Email address" in.
_EMAIL_LABEL = re.compile(r"e-?mail\b")


def new_email_ref() -> str:
    """A tracking ref that survives the trip through a mail provider unchanged."""
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(_REF_LENGTH))


def build_email_alias(address: str, ref: str) -> str:
    """'you@gmail.com' + 'x7k2mp' → 'you+x7k2mp@gmail.com'"""
    local, _, domain = address.partition("@")
    return f"{local}+{ref}@{domain}"


def is_email_label(label: str) -> bool:
    """True for a form label asking for the applicant's email address."""
    return _EMAIL_LABEL.match(label.strip().lower()) is not None
