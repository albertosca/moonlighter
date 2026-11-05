from moonlighter.application.cvgen.latex.render import render_cv
from moonlighter.application.cvgen.pool.loader import CVPool, PoolBullet, PoolExperience

from tests.application.cvgen.latex.render.render_samples import TEMPLATE, make_selection

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


class TestRender:
    def test_fills_summary_and_expertise_escaped(self):
        tex = render_cv(TEMPLATE, make_selection(summary="100% match"), POOL)
        assert r"\cvlistitem{100\% match}" in tex

    def test_experience_renders_selected_bullets_in_selection_order(self):
        tex = render_cv(TEMPLATE, make_selection(), POOL)
        assert tex.index(r"Did \textbf{B}") < tex.index(r"Did \textbf{A}")
        assert r"\cventry{}{Senior Software Developer}{Trybe}" in tex

    def test_prose_entry_renders_when_selected(self):
        tex = render_cv(TEMPLATE, make_selection(), POOL)
        assert "Taught ML." in tex

    def test_open_source_section_only_when_selected(self):
        without = render_cv(TEMPLATE, make_selection(), POOL)
        assert "Open Source" not in without
        with_oss = render_cv(TEMPLATE, make_selection(open_source=("oss-m",)), POOL)
        assert r"\section{Open Source}" in with_oss
        assert r"\textbf{moonlighter}" in with_oss

    def test_pt_translations_replace_bullet_text(self):
        # The translation is plaintext in the **bold** dialect; the pool's own
        # \textbf{A} is markup and is what gets replaced.
        tex = render_cv(
            TEMPLATE,
            make_selection(language="pt", translations={"t-a": "Fiz **A**"}),
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
        tex = render_cv(TEMPLATE, make_selection(translations={"t-a": poisoned}), POOL)
        assert "^^" not in tex
        assert "\\input" not in tex
        assert r"\textasciicircum{}\textasciicircum{}5cinput" in tex  # literal, inert
        assert r"Did \textbf{B}" in tex  # the untranslated pool bullet, untouched

    def test_escaping_covers_bullets_prose_and_open_source(self):
        # All three paths go through _bullet_text; a fix reconciling only one
        # is how the previous silent regression happened.
        poisoned = "^^5cinput^^7b/etc/passwd^^7d"
        tex = render_cv(
            TEMPLATE,
            make_selection(
                open_source=("oss-m",),
                translations={"t-a": poisoned, "igti-prose": poisoned, "oss-m": poisoned},
            ),
            POOL,
        )
        assert "^^" not in tex
        assert "\\input" not in tex
        assert "{/etc/passwd}" not in tex
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
                make_selection(
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
            TEMPLATE, make_selection(translations={"t-a": "Fiz **C** em 30% do tempo"}), POOL
        )
        assert r"Fiz \textbf{C} em 30\% do tempo" in tex

    def test_an_absent_translation_leaves_the_pool_latex_unescaped(self):
        # Escaping the pool's own latex would render \textbf{A} as visible
        # characters in the operator's CV; only a PRESENT translation is escaped.
        tex = render_cv(TEMPLATE, make_selection(translations={}), POOL)
        assert r"Did \textbf{A}" in tex
        assert "textbackslash" not in tex

    def test_open_source_heading_stays_english_in_pt(self):
        # Domain jargon: "Open Source" is untranslated in PT (same convention
        # as pool job titles like "Full Stack Engineer").
        tex = render_cv(
            TEMPLATE,
            make_selection(
                language="pt",
                open_source=("oss-m",),
                translations={"oss-m": "Contribuições em **moonlighter**"},
            ),
            POOL,
        )
        assert r"\section{Open Source}" in tex
        assert r"Contribuições em \textbf{moonlighter}" in tex


class TestFallback:
    def test_experience_with_no_selected_bullets_renders_its_first_pool_bullet(self):
        # Replaces the old "falls back to all": with a one-page budget,
        # rendering every bullet would fight the shrink loop (dropping the last
        # selected bullet of an experience would GROW the document). The period
        # is still never dropped — its first curated bullet stands for it.
        tex = render_cv(TEMPLATE, make_selection(bullets=("igti-prose",)), POOL)
        assert r"Did \textbf{A}" in tex
        assert r"Did \textbf{B}" not in tex
