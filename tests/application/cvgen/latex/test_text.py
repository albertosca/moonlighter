from moonlighter.application.cvgen.latex.text import escape_latex, is_typesettable


class TestEscape:
    def test_escapes_latex_specials(self):
        assert escape_latex("100% of R&D_costs #1") == r"100\% of R\&D\_costs \#1"

    def test_bold_markers_become_textbf(self):
        assert escape_latex("with **10+ years** shipping") == r"with \textbf{10+ years} shipping"

    def test_characters_that_carry_no_text_are_dropped(self):
        # Measured with real pdflatex: each of these is a FATAL error that
        # produces no PDF at all ("Unicode character not set up for use with
        # LaTeX"). None is a TeX special, so escaping alone leaves them in
        # place. They carry no text, so dropping them mangles nothing.
        # Cc splits two ways, and both are fine: Python counts \x1c as
        # whitespace so it collapses to a space, while \x00 and \x7f are not
        # whitespace and are dropped outright. Neither survives into the .tex.
        assert escape_latex("a\x1cb") == "a b"
        assert escape_latex("a\x00b\x7fc") == "abc"
        assert escape_latex("a\u00adb\u200bc\u200ed") == "abcd"  # Cf

    def test_whitespace_runs_collapse_to_a_single_space(self):
        # A blank line inside \cventry's argument is a hard stop: "! Paragraph
        # ended before \cventry was complete", no PDF. The model writing an
        # ordinary "\n\n" is not an attack, so this must not be fatal.
        assert escape_latex("Primeira linha\n\nSegunda linha") == "Primeira linha Segunda linha"
        assert escape_latex("keeps\ttab\nand newline") == "keeps tab and newline"
        # U+2028/U+2029 (Zl/Zp) and exotic spaces are whitespace to Python and
        # fatal to inputenc; collapsing covers them in the same pass.
        assert escape_latex("a\u2028b\u2029c\u2002d") == "a b c d"

    def test_letters_latex_cannot_typeset_are_kept_not_dropped(self):
        # DELIBERATE, and the opposite of the rule above: these carry meaning.
        # Silently deleting a Japanese term or a Greek symbol REWRITES a
        # factual claim in a CV the candidate signs, which the spec forbids
        # outright. escape_latex itself does not judge typesettability — that
        # is is_typesettable's job (called by the generation layer), which
        # rejects the whole field before it ever reaches this renderer. Do not
        # "fix" this by dropping them here.
        for character in ("\u65e5", "\u03a3", "\U0001f680"):
            assert character in escape_latex(f"prefix {character} suffix")

    def test_backslash_input_cannot_inject(self):
        # Exact output: backslash and braces all escaped, no cascade re-escaping
        assert escape_latex(r"\input{evil}") == r"\textbackslash{}input\{evil\}"


class TestTypesettable:
    def test_latin_text_and_common_punctuation_pass(self):
        for text in (
            "Liderou a adoção de IA — 40+ pessoas, ‘pt’ “en” … 100% · Elixir",
            "plain ascii with **bold**",
            "",
        ):
            assert is_typesettable(text), text

    def test_anything_outside_the_latin_allow_list_fails(self):
        # Alberto: "não queremos glifo nenhum no latex, ele tem que ser bem
        # sério". Emoji, CJK, Greek, arrows, check marks, bullets: rejected.
        for character in ("\U0001f680", "日", "Σ", "→", "✓", "•", "Ł"):
            assert not is_typesettable(f"ok {character} ok"), repr(character)

    def test_non_letter_symbols_in_the_latin1_block_are_rejected(self):
        # Tightened 2026-09-04: Latin-1 Supplement admits every accented letter
        # PT/EN need, but the SAME range also carries non-letter symbols (°, ±,
        # §, ×, ÷, ¤, ¦, µ, ¶) that slipped through the earlier "whole block"
        # version. Alberto's bar is "bem sério" — a symbol is no more welcome
        # here than an emoji. € (outside the block entirely) is checked too:
        # rejected, same as before.
        for character in "°±§×÷¤¦µ¶€":
            assert not is_typesettable(f"ok {character} ok"), repr(character)

    def test_the_middle_dot_separator_still_passes(self):
        # · (U+00B7) is the ONE exception: it is the separator the operator's
        # own templates already use between technical_expertise clauses
        # ("GraphQL, REST APIs · PostgreSQL, MySQL"), and it is not the same
        # character as • (U+2022, the bullet Alberto's rule rejects).
        assert is_typesettable("GraphQL, REST APIs · PostgreSQL, MySQL")
