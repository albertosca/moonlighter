"""Pins every line check_cv_pool_floor.main prints, and the exit code that goes with it."""

from unittest.mock import patch

import check_cv_pool_floor
import pytest

from tests.scripts.test_check_cv_pool_floor import POOL_YAML, TEMPLATE


def _configuration(tmp_path, *, with_template=True):
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    if with_template:
        (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    return {"cv": {"pool": str(pool_path), "template_dir": str(template_directory)}}


def _compiling(pages):
    return (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor, "compile_pdf", side_effect=lambda tex: tex.with_suffix(".pdf")
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=pages),
    )


@pytest.mark.parametrize("configuration", [{}, {"cv": None}, {"cv": {}}, {"cv": {"pool": ""}}])
def test_a_missing_pool_setting_stops_with_exit_one(configuration, capsys):
    assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out == "No cv.pool configured — nothing to check.\n"


def test_an_unusable_pool_file_is_reported_with_the_loader_message(tmp_path, capsys):
    configuration = _configuration(tmp_path)
    (tmp_path / "cv-pool.yaml").write_text("experiences: not-a-list\n")

    assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out.startswith("Pool file unusable: ")


def test_a_missing_pool_file_is_reported_as_unusable(tmp_path, capsys):
    configuration = {"cv": {"pool": str(tmp_path / "nowhere.yaml")}}

    assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out.startswith("Pool file unusable: ")


@pytest.mark.parametrize("template_directory", [None, ""])
def test_a_missing_template_directory_setting_stops_with_exit_one(
    tmp_path, capsys, *, template_directory
):
    configuration = _configuration(tmp_path)
    configuration["cv"]["template_dir"] = template_directory

    assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out == "No cv.template_dir configured — nothing to check.\n"


def test_a_directory_without_the_english_template_names_the_expected_file(tmp_path, capsys):
    configuration = _configuration(tmp_path, with_template=False)

    assert check_cv_pool_floor.main(configuration) == 1

    expected = tmp_path / "templates" / "cv-template.en.tex"
    assert capsys.readouterr().out == f"No cv-template.en.tex found at {expected}.\n"


def test_a_check_that_could_not_run_says_so_and_exits_one(tmp_path, capsys):
    configuration = _configuration(tmp_path)

    with patch.object(check_cv_pool_floor, "latex_available", return_value=False):
        assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out == (
        "Could not check: pdflatex not installed, or the floor itself failed to compile.\n"
    )


def test_a_floor_of_one_page_prints_the_fit_line_and_exits_zero(tmp_path, capsys):
    configuration = _configuration(tmp_path)
    latex, compiler, counter = _compiling(1)

    with latex, compiler, counter:
        assert check_cv_pool_floor.main(configuration) == 0

    assert capsys.readouterr().out == "Floor fits: 1 page.\n"


@pytest.mark.parametrize("pages", [2, 3, 0])
def test_any_other_page_count_prints_the_overflow_line_and_exits_one(tmp_path, capsys, *, pages):
    configuration = _configuration(tmp_path)
    latex, compiler, counter = _compiling(pages)

    with latex, compiler, counter:
        assert check_cv_pool_floor.main(configuration) == 1

    assert capsys.readouterr().out == (
        f"Floor overflows: {pages} pages. Every generation for this pool will discard to the "
        "default CV, one wasted LLM call at a time — trim experiences or their bullets.\n"
    )


def test_a_relative_pool_path_resolves_under_the_moonlighter_home(tmp_path, monkeypatch, capsys):
    configuration = _configuration(tmp_path)
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    configuration["cv"]["pool"] = "cv-pool.yaml"
    configuration["cv"]["template_dir"] = "templates"
    latex, compiler, counter = _compiling(1)

    with latex, compiler, counter:
        assert check_cv_pool_floor.main(configuration) == 0

    assert capsys.readouterr().out == "Floor fits: 1 page.\n"
