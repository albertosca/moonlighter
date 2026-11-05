"""Pins what check() measures and refuses to do: the page count, no compile without pdflatex, no count without a pdf."""

from unittest.mock import patch

import check_cv_pool_floor
import pytest

from tests.scripts.check_cv_pool_floor.harness import TEMPLATE, compiling, pool


def _forbidden(name):
    def fail(*_arguments, **_keywords):
        raise AssertionError(f"{name} must not run")

    return fail


@pytest.mark.parametrize("pages", [1, 2])
def test_check_reports_the_page_count_of_the_compiled_floor(tmp_path, *, pages):
    # The whole point of the script: the floor itself — not any one job's
    # selection — is what's measured here, overflowing or not.
    latex, compiler, counter = compiling(pages)

    with latex, compiler, counter:
        assert check_cv_pool_floor.check(pool(tmp_path), TEMPLATE) == pages


def test_check_never_compiles_without_pdflatex(tmp_path):
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=False),
        patch.object(check_cv_pool_floor, "compile_pdf", side_effect=_forbidden("compile_pdf")),
    ):
        assert check_cv_pool_floor.check(pool(tmp_path), TEMPLATE) is None


def test_check_never_counts_pages_of_a_pdf_that_did_not_compile(tmp_path):
    # A broken template (or a pool bullet with unescaped LaTeX that somehow
    # slipped past load_pool's guard) fails the same way a real generation
    # would — reported as "could not check", not crashed.
    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "compile_pdf", return_value=None),
        patch.object(check_cv_pool_floor, "page_count", side_effect=_forbidden("page_count")),
    ):
        assert check_cv_pool_floor.check(pool(tmp_path), TEMPLATE) is None


def test_check_renders_every_experience_via_the_first_bullet_fallback(tmp_path):
    # Proves the floor selection is genuinely empty (bullets=()), not
    # accidentally selecting every bullet — render_cv's own fallback is what
    # produces "one bullet per experience", the exact thing being measured.
    seen = {}

    def spy_compile(tex):
        seen["tex"] = tex.read_text()
        return tex.with_suffix(".pdf")

    with (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(check_cv_pool_floor, "compile_pdf", side_effect=spy_compile),
        patch.object(check_cv_pool_floor, "page_count", return_value=1),
    ):
        check_cv_pool_floor.check(pool(tmp_path), TEMPLATE)
    assert "Did A" in seen["tex"]  # Trybe's first bullet
    assert "Did B" not in seen["tex"]  # not the second — proves it's the floor
    assert "Did C" in seen["tex"]  # AppProva's only bullet


def test_check_renders_the_english_template_with_an_empty_selection(tmp_path):
    floor_pool = pool(tmp_path)
    rendered = {}

    def spy_render(template, selection, rendered_pool):
        rendered.update(template=template, selection=selection, pool=rendered_pool)
        return "\\documentclass{x}"

    latex, compiler, counter = compiling(1)
    with (
        latex,
        patch.object(check_cv_pool_floor, "render_cv", side_effect=spy_render),
        compiler,
        counter,
    ):
        check_cv_pool_floor.check(floor_pool, TEMPLATE)

    selection = rendered["selection"]
    assert (selection.language, selection.summary, selection.technical_expertise) == ("en", "", "")
    assert (selection.bullets, selection.open_source, selection.translations) == ((), (), {})
    assert rendered["template"] == TEMPLATE
    assert rendered["pool"] is floor_pool
