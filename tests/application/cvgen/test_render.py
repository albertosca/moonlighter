import textwrap

from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.render import CVSelection, escape_latex, render_cv

POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Senior Software Developer",
            period="Jan 2023 -- Jul 2026",
            location="BH, Brazil",
            bullets=(
                PoolBullet("t-a", ("backend",), r"Did \textbf{A}"),
                PoolBullet("t-b", ("ai",), r"Did \textbf{B}"),
            ),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        PoolExperience(
            company="IGTI",
            title="Professor",
            period="2018 -- 2019",
            location="BH, Brazil",
            bullets=(),
            prose="Taught ML.",
            prose_id="igti-prose",
            angles=("ai",),
        ),
    ),
    open_source=(PoolBullet("oss-m", ("ai",), r"\textbf{moonlighter}"),),
    summary_facts=(),
)

TEMPLATE = textwrap.dedent(r"""
    \section{Professional Summary}
    \cvlistitem{%%SUMMARY%%}
    \cvlistitem{%%TECHNICAL_EXPERTISE%%}
    %%EXPERIENCE%%
    %%OPEN_SOURCE%%
    \section{Education}
""")


def _selection(**overrides):
    base = {
        "language": "en",
        "summary": "A summary",
        "technical_expertise": "Elixir, React",
        "bullets": ("t-b", "t-a", "igti-prose"),
        "open_source": (),
        "translations": {},
    }
    base.update(overrides)
    return CVSelection(**base)


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
        # A pdflatex document cannot typeset them and the compile dies — but
        # silently deleting a Japanese term or a Greek symbol REWRITES a
        # factual claim in a CV the candidate signs, which the spec forbids
        # outright. The honest outcome is the failed compile, which now
        # degrades to the default CV and regenerates (service._after_compile)
        # instead of being cached forever. Do not "fix" this by dropping them.
        for ch in ("\u65e5", "\u03a3", "\U0001f680"):
            assert ch in escape_latex(f"prefix {ch} suffix")

    def test_backslash_input_cannot_inject(self):
        # Exact output: backslash and braces all escaped, no cascade re-escaping
        assert escape_latex(r"\input{evil}") == r"\textbackslash{}input\{evil\}"


class TestRender:
    def test_fills_summary_and_expertise_escaped(self):
        tex = render_cv(TEMPLATE, _selection(summary="100% match"), POOL)
        assert r"\cvlistitem{100\% match}" in tex

    def test_experience_renders_selected_bullets_in_selection_order(self):
        tex = render_cv(TEMPLATE, _selection(), POOL)
        assert tex.index(r"Did \textbf{B}") < tex.index(r"Did \textbf{A}")
        assert r"\cventry{}{Senior Software Developer}{Trybe}" in tex

    def test_experience_with_no_selected_bullets_falls_back_to_all(self):
        # Spec: an experience whose validated list is empty falls back to the
        # base bullets — dropping a whole employment gap from a CV is worse
        # than generic emphasis.
        tex = render_cv(TEMPLATE, _selection(bullets=("igti-prose",)), POOL)
        assert r"Did \textbf{A}" in tex and r"Did \textbf{B}" in tex

    def test_prose_entry_renders_when_selected(self):
        tex = render_cv(TEMPLATE, _selection(), POOL)
        assert "Taught ML." in tex

    def test_open_source_section_only_when_selected(self):
        without = render_cv(TEMPLATE, _selection(), POOL)
        assert "Open Source" not in without
        with_oss = render_cv(TEMPLATE, _selection(open_source=("oss-m",)), POOL)
        assert r"\section{Open Source}" in with_oss
        assert r"\textbf{moonlighter}" in with_oss

    def test_pt_translations_replace_bullet_text(self):
        # The translation is plaintext in the **bold** dialect; the pool's own
        # \textbf{A} is markup and is what gets replaced.
        tex = render_cv(
            TEMPLATE,
            _selection(language="pt", translations={"t-a": "Fiz **A**"}),
            POOL,
        )
        assert r"Fiz \textbf{A}" in tex
        assert r"Did \textbf{A}" not in tex

    def test_a_translation_is_escaped_while_the_pool_latex_is_not(self):
        # The two strings are not the same kind of text and must not be treated
        # alike: the pool's latex is operator-curated markup and passes through
        # untouched, while a translation is model prose in the **bold** dialect
        # and is escaped here, at the render chokepoint. '^^5c' would be a
        # backslash to TeX's tokenizer, so this is \input{/etc/passwd} unless
        # every one of those characters is neutralised.
        poisoned = "^^5cinput^^7b/etc/passwd^^7d"
        tex = render_cv(TEMPLATE, _selection(translations={"t-a": poisoned}), POOL)
        assert "^^" not in tex and "\\input" not in tex
        assert r"\textasciicircum{}\textasciicircum{}5cinput" in tex  # literal, inert
        assert r"Did \textbf{B}" in tex  # the untranslated pool bullet, untouched

    def test_escaping_covers_bullets_prose_and_open_source(self):
        # All three paths go through _bullet_text; a fix reconciling only one
        # is how the previous silent regression happened.
        poisoned = "^^5cinput^^7b/etc/passwd^^7d"
        tex = render_cv(
            TEMPLATE,
            _selection(
                open_source=("oss-m",),
                translations={"t-a": poisoned, "igti-prose": poisoned, "oss-m": poisoned},
            ),
            POOL,
        )
        assert "^^" not in tex and "\\input" not in tex and "{/etc/passwd}" not in tex
        assert tex.count(r"\textasciicircum{}\textasciicircum{}5cinput") == 3

    def test_bold_markers_in_a_translation_become_textbf(self):
        # The same **bold** dialect the summary already uses — that is what the
        # prompt now asks translations for, so it has to survive escaping.
        tex = render_cv(
            TEMPLATE, _selection(translations={"t-a": "Fiz **C** em 30% do tempo"}), POOL
        )
        assert r"Fiz \textbf{C} em 30\% do tempo" in tex

    def test_an_absent_translation_leaves_the_pool_latex_unescaped(self):
        # Escaping the pool's own latex would render \textbf{A} as visible
        # characters in the operator's CV; only a PRESENT translation is escaped.
        tex = render_cv(TEMPLATE, _selection(translations={}), POOL)
        assert r"Did \textbf{A}" in tex
        assert "textbackslash" not in tex

    def test_open_source_heading_stays_english_in_pt(self):
        # Domain jargon: "Open Source" is untranslated in PT (same convention
        # as pool job titles like "Full Stack Engineer").
        tex = render_cv(
            TEMPLATE,
            _selection(
                language="pt",
                open_source=("oss-m",),
                translations={"oss-m": "Contribuições em **moonlighter**"},
            ),
            POOL,
        )
        assert r"\section{Open Source}" in tex
        assert r"Contribuições em \textbf{moonlighter}" in tex
