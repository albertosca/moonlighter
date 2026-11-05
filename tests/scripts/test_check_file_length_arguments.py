"""Pins main()'s handling of explicit PATH arguments: the ones that select no .py file fail the run."""

from pathlib import Path

import check_file_length
import pytest

from tests.scripts.test_check_file_length import _write_lines, _write_policy


def _output_of_main(
    root: Path, arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    exit_status = check_file_length.main(root, arguments)
    return exit_status, capsys.readouterr().out


def test_a_missing_path_fails_the_run_instead_of_passing_vacuously(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/small.py", 2)

    assert _output_of_main(tmp_path, ["no/such/path"], capsys) == (
        1,
        "File length gate failed:\n  - no/such/path: selects no .py file\n",
    )


def test_a_file_that_is_not_python_selects_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "notes.txt").write_text("".join(f"line {number}\n" for number in range(20)))

    assert _output_of_main(tmp_path, ["notes.txt"], capsys) == (
        1,
        "File length gate failed:\n  - notes.txt: selects no .py file\n",
    )


def test_a_directory_without_python_files_selects_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/page.md").write_text("# page\n")
    _write_lines(tmp_path, "packages/core/.venv/site.py", 50)

    assert _output_of_main(tmp_path, ["docs", "packages/core/.venv"], capsys) == (
        1,
        (
            "File length gate failed:\n"
            "  - docs: selects no .py file\n"
            "  - packages/core/.venv: selects no .py file\n"
        ),
    )


@pytest.mark.parametrize("form", ["absolute", "parent"])
def test_a_path_outside_the_repository_selects_nothing_and_never_raises(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], form: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _write_policy(repository)
    _write_lines(tmp_path, "outside/big.py", 6)
    argument = str(tmp_path / "outside/big.py") if form == "absolute" else "../outside/big.py"

    assert _output_of_main(repository, [argument], capsys) == (
        1,
        f"File length gate failed:\n  - {argument}: selects no .py file\n",
    )


def test_an_absolute_path_inside_the_repository_is_measured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "scripts/big.py", 6)

    status, output = _output_of_main(tmp_path, [str(tmp_path / "scripts/big.py")], capsys)

    assert status == 1
    assert output.splitlines()[1].startswith("  - scripts/big.py has 6 lines;")


def test_rejected_arguments_come_first_in_argument_order_then_the_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "scripts/big.py", 6)

    assert _output_of_main(tmp_path, ["gone-b", "scripts/big.py", "gone-a"], capsys) == (
        1,
        (
            "File length gate failed:\n"
            "  - gone-b: selects no .py file\n"
            "  - gone-a: selects no .py file\n"
            "  - scripts/big.py has 6 lines; the limit is 5 (justify it in pyproject.toml or split it)\n"
        ),
    )


def test_a_valid_argument_alone_still_passes_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "scripts/small.py", 2)

    assert _output_of_main(tmp_path, ["scripts/small.py"], capsys) == (
        0,
        "Every Python file is within 5 lines.\n",
    )


def test_a_rejected_argument_does_not_fall_back_to_the_default_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/big.py", 7)

    assert _output_of_main(tmp_path, ["no/such/path"], capsys) == (
        1,
        "File length gate failed:\n  - no/such/path: selects no .py file\n",
    )
