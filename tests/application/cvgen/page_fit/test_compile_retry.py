from unittest.mock import patch

from moonlighter.application.cvgen.page_fit import TailoredCV
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.tailored_cv_samples import JOB, counting_caller


async def test_no_latex_returns_tex_uncompiled(config):
    call, _ = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=False),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert result is not None
    assert not result.compiled
    assert result.path.suffix == ".tex"


async def test_existing_tex_retries_compile_and_succeeds(config):
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = counting_caller()
    with patch(
        "moonlighter.application.cvgen.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert result == TailoredCV(out / "cv.pdf", compiled=True)
    assert calls["n"] == 0


async def test_existing_tex_retries_compile_and_stays_uncompiled(config):
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=False),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert result == TailoredCV(out / "cv.tex", compiled=False)
    assert calls["n"] == 0


async def test_a_tex_that_cannot_compile_is_discarded_not_cached(config, caplog):
    # compile_pdf returning None means two different things. With pdflatex on
    # the machine it means THIS DOCUMENT does not compile — it will fail
    # identically forever, so keeping the .tex turns one unlucky generation
    # into a permanently broken tailored CV for this job.
    call, _ = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert result is None  # degrades to the default CV, per the spec
    assert not (generated_dir_for(config, 42) / "cv.tex").exists()


async def test_three_consecutive_prepares_regenerate_instead_of_re_failing(config):
    # The measured bug: prepares 2 and 3 made ZERO llm calls and re-failed on
    # the cached .tex. Regeneration is what makes the failure transient.
    call, calls = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=True),
    ):
        for _ in range(3):
            assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 3


async def test_a_tex_kept_for_a_missing_latex_compiles_later_without_an_llm_call(config):
    # The legitimate case the short-circuit exists for, preserved end to end:
    # prepare 1 on a machine with no pdflatex keeps the .tex; prepare 2, after
    # latex is installed, compiles that same file and spends nothing.
    call, calls = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=False),
    ):
        first = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert first is not None
    assert not first.compiled
    with patch(
        "moonlighter.application.cvgen.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        second = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert second is not None
    assert second.compiled
    assert calls["n"] == 1  # the second prepare reused the cached .tex


async def test_a_partial_pdf_left_by_a_failed_compile_is_discarded_with_the_tex(config):
    # A timeout SIGKILLs pdflatex mid-write, so a truncated cv.pdf survives on
    # disk while compile_pdf still returns None. Leaving it there is worse than
    # the bug round 5 fixed, because the cache short-circuits on cv.pdf BEFORE
    # any compile: every later prepare hands the operator a corrupt file at
    # zero LLM calls, with the source .tex already deleted. 12 tests in this
    # file patch compile_pdf and not one staged a .pdf beside it, which is why
    # the suite could not see this.
    def timeout_like(tex):
        # Exactly what a timeout does: pdflatex is SIGKILLed mid-write, so a
        # truncated .pdf is on disk while compile_pdf still answers None.
        tex.with_suffix(".pdf").write_bytes(b"%PDF-1.7\ntruncated, no EOF marker")

    call, calls = counting_caller()
    with (
        patch("moonlighter.application.cvgen.page_fit.compile_pdf", side_effect=timeout_like),
        patch("moonlighter.application.cvgen.page_fit.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    out = generated_dir_for(config, 42)
    assert not (out / "cv.tex").exists()
    assert not (out / "cv.pdf").exists()  # the corrupt file must not survive
    with patch(
        "moonlighter.application.cvgen.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        second = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert second is not None
    assert second.compiled
    assert calls["n"] == 2  # one call per prepare: nothing was served from cache
