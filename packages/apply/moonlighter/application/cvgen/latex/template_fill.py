"""Fills the shipped generic CV template's one-time placeholders from profile.yaml.

All deterministic substitution, no model call: name, contact and education.
"""

import importlib.resources
import re
from typing import Any

from moonlighter.application.cvgen.latex.text import escape_latex
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

# The ONE substitution fill_template leaves unescaped, on the reasoning that
# a LinkedIn slug is never free text -- so the pattern has to actually be a
# slug, which "anything but /?#" was not: it happily captured a '%' (LaTeX's
# comment character, which silently eats the rest of the line) or a '\' out
# of a malformed profile.yaml and pasted it straight into \social[linkedin]{}.
# A real vanity slug is letters, digits and hyphens. The lookahead is what
# makes the tightening safe rather than lossy: without it the pattern would
# match the ASCII PREFIX of a percent-encoded international slug and silently
# put a truncated, wrong handle on the CV. Anchored to the end of the path
# segment, a slug that is not a slug matches nothing and degrades to an empty
# \social{} -- announced, not silent.
_LINKEDIN_USERNAME = re.compile(r"linkedin\.com/in/([A-Za-z0-9-]+)(?=[/?#]|$)")

# A name is split on its last space into a first and a last name.
_NAME_PARTS = 2


def _split_name(name: str) -> tuple[str, str]:
    parts = name.strip().rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == _NAME_PARTS else (name.strip(), "")


def _linkedin_username(url: str) -> str:
    match = _LINKEDIN_USERNAME.search(url)
    if match is not None:
        return match.group(1)
    if url.strip():
        logger.warning(
            "bootstrap: profile.yaml's linkedin value is not a recognizable profile URL "
            "— leaving the CV's LinkedIn field empty"
        )
    return ""


def _education_block(entries: list[Any]) -> str:
    # year/degree/school are pasted into \cventry{...} the same way pool.py's
    # curated company/title/location are (see that module's own docstring for
    # the "R&D Engineer" incident this class of bug already caused once) --
    # profile.yaml is operator-authored free text, not pre-escaped LaTeX, so
    # every field goes through escape_latex exactly like the contact fields
    # below.
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        year = escape_latex(str(entry.get("year") or ""))
        degree = escape_latex(str(entry.get("degree") or ""))
        school = escape_latex(str(entry.get("school") or ""))
        lines.append(f"\\cventry{{{year}}}{{{degree}}}{{{school}}}{{}}{{}}{{}}")
    return "\n".join(lines)


def fill_template(profile: dict[str, Any]) -> str:
    """Fills the shipped generic template's ONE-TIME {{...}} placeholders from profile.yaml.

    Name/contact/education, all deterministic substitution, no LLM call. The
    four per-job %%...%% markers are untouched: they are filled on every
    prepare_application call, by render_cv, not here.
    """
    templates = importlib.resources.files("moonlighter.application.cvgen.templates")
    text = (templates / "cv-template.en.example.tex").read_text()
    first, last = _split_name(str(profile.get("name") or ""))
    # These five substitute into ordinary text-mode LaTeX macros (\firstname{},
    # \title{}, \phone[mobile]{}, \email{}), never verbatim -- an unescaped
    # '&'/'%'/'_' from a profile field either breaks the compile or, worse, a
    # bare '%' silently truncates the rest of the line (LaTeX's comment
    # character) with no compile error at all. escape_latex is what pool.py's
    # own curated fields and every model-authored string in render.py already
    # go through before reaching a .tex file; profile.yaml is exactly as
    # untrusted as either. LINKEDIN_USERNAME is the one exception: it is a
    # slug already parsed out of a URL by _linkedin_username, never free text,
    # and moderncv's \social[linkedin]{...} expects exactly that bare slug.
    return (
        text.replace("{{NAME_FIRST}}", escape_latex(first))
        .replace("{{NAME_LAST}}", escape_latex(last))
        .replace("{{HEADLINE}}", escape_latex(str(profile.get("headline") or "")))
        .replace("{{PHONE}}", escape_latex(str(profile.get("phone") or "")))
        .replace("{{EMAIL}}", escape_latex(str(profile.get("email") or "")))
        .replace("{{LINKEDIN_USERNAME}}", _linkedin_username(str(profile.get("linkedin") or "")))
        .replace("{{EDUCATION}}", _education_block(profile.get("education") or []))
    )
