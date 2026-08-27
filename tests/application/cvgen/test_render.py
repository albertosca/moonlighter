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
        tex = render_cv(
            TEMPLATE,
            _selection(language="pt", translations={"t-a": r"Fiz \textbf{A}"}),
            POOL,
        )
        assert r"Fiz \textbf{A}" in tex
        assert r"Did \textbf{A}" not in tex

    def test_a_translation_outside_the_grammar_falls_back_to_the_pool_latex(self, caplog):
        # Defence in depth. decide_cv validates too, but _bullet_text is the
        # chokepoint EVERY model-controlled unescaped string passes just before
        # substitution — validating here makes the curated fallback the default
        # instead of something each future producer of a CVSelection must
        # remember. '^^5c' is a backslash to TeX's tokenizer, so this is
        # \input{/etc/passwd} by the time pdflatex reads it.
        poisoned = "^^5cinput^^7b/etc/passwd^^7d"
        tex = render_cv(TEMPLATE, _selection(translations={"t-a": poisoned}), POOL)
        assert poisoned not in tex
        assert r"Did \textbf{A}" in tex  # the curated bullet, untouched
        assert any("translation" in r.message for r in caplog.records)

    def test_the_render_time_fallback_covers_bullets_prose_and_open_source(self):
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
        assert "^^" not in tex and "input" not in tex
        assert r"Did \textbf{A}" in tex  # bullet path fell back
        assert "Taught ML." in tex  # prose path fell back
        assert r"\textbf{moonlighter}" in tex  # open-source path fell back

    def test_open_source_heading_stays_english_in_pt(self):
        # Domain jargon: "Open Source" is untranslated in PT (same convention
        # as pool job titles like "Full Stack Engineer").
        tex = render_cv(
            TEMPLATE,
            _selection(
                language="pt",
                open_source=("oss-m",),
                translations={"oss-m": r"Contribuições em \textbf{moonlighter}"},
            ),
            POOL,
        )
        assert r"\section{Open Source}" in tex
        assert r"Contribuições em \textbf{moonlighter}" in tex
