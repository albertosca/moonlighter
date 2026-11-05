"""Where model text becomes inert, the one place that makes it safe for a .tex file.

Everything the model authors (summary, technical expertise, translations,
drafted bullets, the profile's own free text) passes through `escape_latex`
before it can reach a document, and `is_typesettable` decides first whether a
field may be used at all. Escaping rewrites every TeX special, so nothing the
model writes can become a command; there is no "trusted markup" path.
"""

import re
import unicodedata

# Single-pass lookup table prevents cascade re-escaping: braces produced by
# \textbackslash{} cannot be re-escaped on a subsequent pass.
_LATEX_ESCAPE_TABLE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_BOLD = re.compile(r"\*\*(.+?)\*\*")

# Three classes of character are not TeX specials, so escaping leaves them
# untouched, and each is a FATAL pdflatex error that yields no PDF at all
# (measured, not assumed):
#   - a blank line inside \cventry's argument — "! Paragraph ended before
#     \cventry was complete". An ordinary "\n\n" from the model triggers it.
#   - U+2028/U+2029 and exotic spaces (U+2002...) — "Unicode character not set
#     up for use with LaTeX".
#   - control (Cc) and format (Cf: U+200B, U+200E, soft hyphen) characters.
# All three carry no text, so collapsing and dropping them mangles nothing.
# Whitespace collapsing runs first and absorbs everything Python calls
# whitespace (newlines, tabs, Zl, Zp, Zs); the category pass then removes what
# is left, which is the non-whitespace Cc and every Cf.
#
# What is deliberately NOT dropped: letters LaTeX cannot typeset (CJK, Greek,
# emoji). Those carry meaning, and silently deleting one REWRITES a factual
# claim in a document the candidate signs. is_typesettable (called by the
# generation layer, before a field ever reaches this renderer) rejects such a
# field whole instead.
_WHITESPACE = re.compile(r"\s+")
_DROPPED_CATEGORIES = frozenset({"Cc", "Cf"})

# Alberto's rule for the document: no glyph outside Latin text, ever. Printable
# ASCII, Latin-1 Supplement LETTERS ONLY (xc0-xd6, xd8-xf6, xf8-xff — every
# accented letter PT and EN need, skipping the two non-letter codepoints in
# that span, U+00D7 and U+00F7), the two dashes, curly quotes and the
# ellipsis. Tightened 2026-09-04 (Alberto): the earlier "whole Latin-1 block"
# version also let through non-letter symbols in the same range (U+00B0,
# U+00B1, U+00A7, U+00A4, U+00A6, U+00B5, U+00B6 and the like) — no more
# welcome here than an emoji. The one deliberate exception is U+00B7 (NOT
# U+2022, the bullet Alberto's rule rejects): it is the separator the
# operator's own templates already use between technical_expertise clauses.
# Anything else outside this set fails the whole field; generate.py then
# substitutes curated text for it. Nothing is stripped — stripping rewrites
# a claim.
_TYPESETTABLE = re.compile(
    r"^[\x20-\x7e\xc0-\xd6\xd8-\xf6\xf8-\xff\xb7\u2013\u2014\u2018\u2019\u201c\u201d\u2026]*$"
)


def is_typesettable(text: str) -> bool:
    """Whether every character is inside the Latin allow-list.

    Checked AFTER whitespace collapse and Cc/Cf drop (escape_latex's first
    two passes), so a stray newline or zero-width space never fails a field
    that is otherwise fine — those carry no text and are removed anyway.
    """
    text = _WHITESPACE.sub(" ", text)
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) not in _DROPPED_CATEGORIES
    )
    return _TYPESETTABLE.fullmatch(text) is not None


def escape_latex(text: str) -> str:
    # Single-pass regex prevents cascade: braces in \textbackslash{} won't
    # be re-escaped to \{ and \}.
    text = _WHITESPACE.sub(" ", text).strip()
    # .strip() LAST, not only after the collapse: dropping Cc/Cf re-exposes
    # whitespace that was interior a moment ago ("<ZWSP> <ZWSP>" leaves a lone
    # space), and a truthy " " defeats the empty-translation fallback in
    # _bullet_text — "\item " is legal LaTeX, so nothing downstream notices the
    # line has silently vanished. Also trims that residue from the summary and
    # technical-expertise fields, which have no fallback at all.
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) not in _DROPPED_CATEGORIES
    ).strip()
    text = re.sub(r"[\\&%$#_{}~^]", lambda match: _LATEX_ESCAPE_TABLE[match.group()], text)
    return _BOLD.sub(r"\\textbf{\1}", text)
