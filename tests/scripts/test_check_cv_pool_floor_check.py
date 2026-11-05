"""Pins what check() does and refuses to do: no compile without pdflatex, no page count without a pdf, and the empty selection."""

from unittest.mock import patch

import check_cv_pool_floor

from tests.scripts.test_check_cv_pool_floor import TEMPLATE, _pool


def _forbidden(name):
    def fail(*_arguments, **_keywords):
        raise AssertionError(f"{name} must not run")

    return fail


def test_check_never_compiles_without_pdflatex(tmp_path):
    pool = _pool(tmp_path)
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=False),
        patch.object(check_cv_pool_floor, "compile_pdf", side_effect=_forbidden("compile_pdf")),
    ):
        assert check_cv_pool_floor.check(pool, TEMPLATE) is None


def test_check_never_counts_pages_of_a_pdf_that_did_not_compile(tmp_path):
    pool = _pool(tmp_path)
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "compile_pdf", return_value=None),
        patch.object(check_cv_pool_floor, "page_count", side_effect=_forbidden("page_count")),
    ):
        assert check_cv_pool_floor.check(pool, TEMPLATE) is None


def test_check_renders_the_english_template_with_an_empty_selection(tmp_path):
    pool = _pool(tmp_path)
    rendered = {}

    def spy_render(template, selection, rendered_pool):
        rendered.update(template=template, selection=selection, pool=rendered_pool)
        return "\\documentclass{x}"

    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "render_cv", side_effect=spy_render),
        patch.object(
            check_cv_pool_floor, "compile_pdf", side_effect=lambda tex: tex.with_suffix(".pdf")
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=1),
    ):
        check_cv_pool_floor.check(pool, TEMPLATE)

    selection = rendered["selection"]
    assert (selection.language, selection.summary, selection.technical_expertise) == ("en", "", "")
    assert (selection.bullets, selection.open_source, selection.translations) == ((), (), {})
    assert rendered["template"] == TEMPLATE
    assert rendered["pool"] is pool
