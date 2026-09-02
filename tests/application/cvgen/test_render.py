import textwrap

from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.render import (
    CVSelection,
    escape_latex,
    is_typesettable,
    render_cv,
)

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
        # Silently deleting a Japanese term or a Greek symbol REWRITES a
        # factual claim in a CV the candidate signs, which the spec forbids
        # outright. escape_latex itself does not judge typesettability — that
        # is is_typesettable's job (called by the generation layer), which
        # rejects the whole field before it ever reaches this renderer. Do not
        # "fix" this by dropping them here.
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

    def test_an_empty_translation_falls_back_to_the_pool_latex(self):
        # Whitespace-only or zero-width-only input escapes to "", and the
        # fallback triggered on None alone — so the bullet rendered EMPTY,
        # silently deleting a line from the CV. Empty is not a translation.
        #
        # The MIXED forms are why the strip has to run last. Whitespace is
        # collapsed and stripped first, then Cc/Cf are dropped — so a ZWSP on
        # either side of a space leaves a lone ' ' AFTER the drop, which is
        # truthy, so the fallback never fires and "\item " renders. That is
        # legal LaTeX, so the compile-failure net never catches it either: a
        # line silently vanishes from a document the candidate signs.
        blanks = (
            "\u200b\u200b",
            "   ",
            "\n\n",
            "\u00ad",
            "",
            "\u200b \u200b",  # ZWSP  space  ZWSP
            "\u00ad \u00ad",  # SHY   space  SHY
            "\u200e \u200e",  # LRM   space  LRM
            "\u200b\n\u200b",  # around a newline
            "\u200b\t\u200b",  # around a tab
        )
        for blank in blanks:
            tex = render_cv(
                TEMPLATE,
                _selection(
                    open_source=("oss-m",),
                    translations={"t-a": blank, "igti-prose": blank, "oss-m": blank},
                ),
                POOL,
            )
            # all three render paths go through _bullet_text, so all three
            # must keep their curated content
            assert r"Did \textbf{A}" in tex, f"lost the bullet for {blank!r}"
            assert "Taught ML." in tex, f"lost the prose for {blank!r}"
            assert r"\textbf{moonlighter}" in tex, f"lost the open-source item for {blank!r}"

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


GROUPED_POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Senior Software Developer",
            period="Jan 2023 -- Jul 2026",
            location="BH, Brazil",
            bullets=(PoolBullet("t-ic", ("backend",), "IC work"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        PoolExperience(
            company="Trybe",
            title="Engineering Manager",
            period="Sep 2019 -- Dec 2022",
            location="BH, Brazil",
            bullets=(PoolBullet("t-em", ("leadership",), "EM work"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
        PoolExperience(
            company="AppProva",
            title="Full Stack Engineer / Tech Lead",
            period="Jun 2017 -- Sep 2019",
            location="BH, Brazil",
            bullets=(PoolBullet("a-1", ("backend",), "Built X"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(),
    summary_facts=(),
)


class TestGrouping:
    def test_consecutive_roles_at_one_company_render_as_one_block(self):
        # moderncv banking's own multi-role form: company, overall span and
        # location on the first entry's bold line, each role's own period in
        # the first argument (the italic line); following roles omit company,
        # span and location so the bold line is skipped.
        tex = render_cv(TEMPLATE, _selection(bullets=("t-ic", "t-em", "a-1")), GROUPED_POOL)
        assert (
            r"\cventry{Jan 2023 -- Jul 2026}{Senior Software Developer}{Trybe}"
            r"{Sep 2019 -- Jul 2026}{BH, Brazil}{" in tex
        )
        assert r"\cventry{Sep 2019 -- Dec 2022}{Engineering Manager}{}{}{}{" in tex
        assert tex.count("{Trybe}") == 1

    def test_a_single_role_company_keeps_the_plain_form(self):
        tex = render_cv(TEMPLATE, _selection(bullets=("t-ic", "t-em", "a-1")), GROUPED_POOL)
        assert (
            r"\cventry{}{Full Stack Engineer / Tech Lead}{AppProva}{Jun 2017 -- Sep 2019}"
            r"{BH, Brazil}{" in tex
        )

    def test_grouping_needs_adjacency(self):
        # Trybe, AppProva, Trybe: the two Trybe entries are not one block.
        shuffled = CVPool(
            experiences=(
                GROUPED_POOL.experiences[0],
                GROUPED_POOL.experiences[2],
                GROUPED_POOL.experiences[1],
            ),
            open_source=(),
            summary_facts=(),
        )
        tex = render_cv(TEMPLATE, _selection(bullets=("t-ic", "t-em", "a-1")), shuffled)
        assert tex.count("{Trybe}") == 2
        assert "{}{}{}{" not in tex


class TestFallback:
    def test_experience_with_no_selected_bullets_renders_its_first_pool_bullet(self):
        # Replaces the old "falls back to all": with a one-page budget,
        # rendering every bullet would fight the shrink loop (dropping the last
        # selected bullet of an experience would GROW the document). The period
        # is still never dropped — its first curated bullet stands for it.
        tex = render_cv(TEMPLATE, _selection(bullets=("igti-prose",)), POOL)
        assert r"Did \textbf{A}" in tex
        assert r"Did \textbf{B}" not in tex


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
        for ch in ("\U0001f680", "日", "Σ", "→", "✓", "•", "Ł"):
            assert not is_typesettable(f"ok {ch} ok"), repr(ch)
