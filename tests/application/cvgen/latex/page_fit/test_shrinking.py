import json
from unittest.mock import patch

from moonlighter.application.cvgen.latex.page_fit import TailoredCV
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv
from tests.application.cvgen.latex.page_fit.pdf_compilers import compiler_that_reports
from tests.application.cvgen.tailored_cv_samples import JOB, counting_caller, write_pool

WIDE_POOL_YAML = """
experiences:
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
      - id: t-b
        angles: [backend]
        latex: 'Did B'
      - id: t-c
        angles: [backend]
        latex: 'Did C'
open_source:
  - id: oss-m
    angles: [ai]
    latex: 'moonlighter'
"""


WIDE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a", "t-b", "t-c"],
        "open_source": ["oss-m"],
    }
)


async def test_a_two_page_cv_is_shrunk_until_it_fits(config):
    write_pool(config, WIDE_POOL_YAML)
    call, calls = counting_caller(WIDE_GENERATE)
    compile_, attempts = compiler_that_reports([2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    assert attempts["n"] == 3
    assert calls["n"] == 1  # shrinking never spends another LLM call
    tex = (generated_dir_for(config, 42) / "cv.tex").read_text()
    # dropped from the end, in the model's order: t-c first, then t-b
    assert "Did A" in tex
    assert "Did B" not in tex
    assert "Did C" not in tex
    assert "moonlighter" in tex  # open source survives while a bullet could go


async def test_open_source_goes_only_when_no_bullet_can(config):
    write_pool(config, WIDE_POOL_YAML)
    call, _ = counting_caller(WIDE_GENERATE)
    compile_, _attempts = compiler_that_reports([2, 2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    tex = (generated_dir_for(config, 42) / "cv.tex").read_text()
    assert "Did A" in tex  # the experience keeps at least one bullet
    assert "moonlighter" not in tex


async def test_a_cv_that_never_fits_is_discarded_like_a_non_compiling_one(config, caplog):
    write_pool(config, WIDE_POOL_YAML)
    call, _ = counting_caller(WIDE_GENERATE)
    compile_, _attempts = compiler_that_reports([2])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    out = generated_dir_for(config, 42)
    assert not (out / "cv.tex").exists()
    assert not (out / "cv.pdf").exists()
    assert not (out / "cv.log").exists()  # page_count reads this; no stale log survives
    assert any("one page" in record.message for record in caplog.records)


async def test_a_cached_tex_that_compiles_to_two_pages_is_discarded(config):
    # The "machine gained latex" path has no selection to shrink; a cached
    # document that overflows is discarded so the next prepare regenerates
    # under the budget instead of serving two pages forever.
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = counting_caller()
    compile_, _attempts = compiler_that_reports([2])
    with (
        patch("moonlighter.application.cvgen.latex.page_fit.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert not (out / "cv.tex").exists()
    assert not (out / "cv.pdf").exists()
    assert calls["n"] == 0


async def test_no_page_count_is_accepted_as_is(config):
    # A compile_pdf that leaves no log (every existing test's stand-in) is
    # trusted: the log is evidence of overflow, its absence is not.
    call, _ = counting_caller()
    with patch(
        "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
