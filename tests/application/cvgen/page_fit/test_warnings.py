from unittest.mock import patch

from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.log_records import logged_warnings
from tests.application.cvgen.tailored_cv_samples import GENERATE_TWO_BULLETS, JOB, fixed_caller

PAGE_FIT = "moonlighter.application.cvgen.page_fit"


def _pages_reported(counts):
    reports = iter(counts)

    def compile_(tex):
        return tex.with_suffix(".pdf")

    return compile_, lambda _tex: next(reports)


async def test_a_document_that_does_not_compile_is_discarded_with_its_path(config, caplog):
    tex = generated_dir_for(config, 42) / "cv.tex"
    with (
        patch(f"{PAGE_FIT}.compile_pdf", return_value=None),
        patch(f"{PAGE_FIT}.latex_available", return_value=True),
    ):
        assert (
            await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS))
            is None
        )
    assert logged_warnings(caplog) == [
        f"the generated CV does not compile — discarding {tex}, using default CV"
    ]


async def test_a_cached_cv_over_one_page_is_discarded_with_its_path(config, caplog):
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("x")
    _compile, pages = _pages_reported([2])
    with (
        patch(f"{PAGE_FIT}.compile_pdf", side_effect=_compile),
        patch(f"{PAGE_FIT}.page_count", side_effect=pages),
    ):
        assert (
            await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS))
            is None
        )
    assert logged_warnings(caplog) == [
        f"the cached CV does not fit one page — discarding {out / 'cv.tex'}, using default CV"
    ]


async def test_a_cv_that_never_fits_names_the_minimum_in_its_warning(config, caplog):
    tex = generated_dir_for(config, 42) / "cv.tex"
    _compile, pages = _pages_reported([2, 2])
    with (
        patch(f"{PAGE_FIT}.compile_pdf", side_effect=_compile),
        patch(f"{PAGE_FIT}.page_count", side_effect=pages),
        patch(f"{PAGE_FIT}.latex_available", return_value=True),
    ):
        assert (
            await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_TWO_BULLETS))
            is None
        )
    assert logged_warnings(caplog) == [
        (
            "the generated CV does not fit one page even at minimum — "
            f"discarding {tex}, using default CV"
        )
    ]
