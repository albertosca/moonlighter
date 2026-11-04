"""Tests for scripts/check_file_length.py, the repository's file-length gate."""

import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def checker() -> ModuleType:
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import check_file_length  # noqa: PLC0415 - scripts/ is not a package; importable only after the path insert

    return check_file_length


def _write_policy(root: Path, justified: dict[str, str] | None = None) -> None:
    entries = "\n".join(f'"{path}" = "{reason}"' for path, reason in (justified or {}).items())
    (root / "pyproject.toml").write_text(
        textwrap.dedent("""\
            [tool.moonlighter.file-length]
            limit = 5
            ceiling = 8

            [tool.moonlighter.file-length.justified]
            """)
        + entries
        + "\n"
    )


def _write_lines(root: Path, relative_path: str, count: int) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line_{number} = {number}\n" for number in range(count)))


def test_files_at_the_limit_pass(tmp_path: Path, checker: ModuleType) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/small.py", 5)

    assert checker.check(tmp_path) == []


def test_a_file_over_the_limit_without_justification_is_reported(
    tmp_path: Path, checker: ModuleType
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/big.py", 6)

    assert checker.check(tmp_path) == [
        "packages/core/big.py has 6 lines; the limit is 5 (justify it in pyproject.toml or split it)"
    ]


def test_a_justified_file_between_limit_and_ceiling_passes(
    tmp_path: Path, checker: ModuleType
) -> None:
    _write_policy(tmp_path, {"tests/test_big.py": "one catalogue of parser cases"})
    _write_lines(tmp_path, "tests/test_big.py", 8)

    assert checker.check(tmp_path) == []


def test_a_file_over_the_ceiling_fails_even_when_justified(
    tmp_path: Path, checker: ModuleType
) -> None:
    _write_policy(tmp_path, {"scripts/huge.py": "historical"})
    _write_lines(tmp_path, "scripts/huge.py", 9)

    assert checker.check(tmp_path) == [
        "scripts/huge.py has 9 lines; nothing may exceed the ceiling of 8, justified or not"
    ]


def test_a_justification_without_a_reason_is_reported(tmp_path: Path, checker: ModuleType) -> None:
    _write_policy(tmp_path, {"packages/core/big.py": "  "})
    _write_lines(tmp_path, "packages/core/big.py", 7)

    assert checker.check(tmp_path) == [
        "packages/core/big.py is justified with an empty reason in pyproject.toml"
    ]


def test_a_justification_for_a_file_back_under_the_limit_is_stale(
    tmp_path: Path, checker: ModuleType
) -> None:
    _write_policy(tmp_path, {"packages/core/shrunk.py": "was a big parser"})
    _write_lines(tmp_path, "packages/core/shrunk.py", 3)

    assert checker.check(tmp_path) == [
        "packages/core/shrunk.py is justified in pyproject.toml but has 3 lines; delete the entry"
    ]


def test_a_justification_for_a_missing_file_is_stale(tmp_path: Path, checker: ModuleType) -> None:
    _write_policy(tmp_path, {"packages/core/gone.py": "moved away"})

    assert checker.check(tmp_path) == [
        "packages/core/gone.py is justified in pyproject.toml but does not exist; delete the entry"
    ]


def test_virtualenvs_and_bytecode_caches_are_never_measured(
    tmp_path: Path, checker: ModuleType
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/.venv/lib/site.py", 50)
    _write_lines(tmp_path, "tests/__pycache__/generated.py", 50)

    assert checker.check(tmp_path) == []


def test_only_the_requested_paths_are_checked(tmp_path: Path, checker: ModuleType) -> None:
    _write_policy(tmp_path, {"packages/scan/gone.py": "stale, but outside the request"})
    _write_lines(tmp_path, "packages/core/big.py", 6)
    _write_lines(tmp_path, "packages/scan/big.py", 6)

    assert checker.check(tmp_path, [Path("packages/core")]) == [
        "packages/core/big.py has 6 lines; the limit is 5 (justify it in pyproject.toml or split it)"
    ]


def test_a_single_requested_file_is_checked(tmp_path: Path, checker: ModuleType) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "scripts/big.py", 6)

    assert len(checker.check(tmp_path, [Path("scripts/big.py")])) == 1


def test_main_exits_zero_and_says_so_when_every_file_fits(
    tmp_path: Path, checker: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/small.py", 2)

    assert checker.main(tmp_path, []) == 0
    assert capsys.readouterr().out == "Every Python file is within 5 lines.\n"


def test_main_exits_one_and_lists_every_violation(
    tmp_path: Path, checker: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_policy(tmp_path)
    _write_lines(tmp_path, "packages/core/big.py", 6)

    assert checker.main(tmp_path, []) == 1
    assert capsys.readouterr().out == (
        "File length gate failed:\n"
        "  - packages/core/big.py has 6 lines; the limit is 5 (justify it in pyproject.toml or split it)\n"
    )
