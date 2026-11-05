"""Pins check_readme_facts.main(): argument handling, the OK line, the problem lines and their order."""

from pathlib import Path

import check_readme_facts
import pytest

GOOD_BLOCK = "<!-- facts -->1,000+ tests · 100% gate · 2 packages<!-- /facts -->\n"


def _repository(root: Path, *, tests: int = 1000) -> Path:
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = \"--cov-fail-under=100 -m 'not e2e'\"\n"
    )
    for name in ("core", "scan"):
        (root / "packages" / name).mkdir(parents=True)
        (root / "packages" / name / "pyproject.toml").write_text("")
    for relative in check_readme_facts.FACT_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(GOOD_BLOCK)
    (root / "report.xml").write_text(f'<testsuite tests="{tests}"/>')
    return root


def test_main_prints_the_ok_line_with_the_real_numbers(tmp_path, capsys):
    repository = _repository(tmp_path, tests=1100)

    exit_code = check_readme_facts.main(
        ["x", "--junit", str(repository / "report.xml"), "--repo", str(repository)]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "README facts and links OK (1100 tests, 100% gate, 2 packages).\n"
    assert captured.err == ""


def test_the_flags_may_come_in_either_order(tmp_path, capsys):
    repository = _repository(tmp_path)

    exit_code = check_readme_facts.main(
        ["x", "--repo", str(repository), "--junit", str(repository / "report.xml")]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("README facts and links OK (1000 tests")


def test_main_prints_fact_problems_before_link_problems_in_file_order(tmp_path, capsys):
    repository = _repository(tmp_path)
    (repository / "guide/en/llms.txt").write_text("no block here\n")
    (repository / "README.pt.md").write_text(GOOD_BLOCK + "[gone](missing.md)\n")
    (repository / "README.md").write_text(GOOD_BLOCK + '<img src="assets/x.svg">\n')

    exit_code = check_readme_facts.main(
        ["x", "--junit", str(repository / "report.xml"), "--repo", str(repository)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "guide/en/llms.txt: expected exactly one facts block, found 0",
        "README.md: assets/x.svg does not exist",
        "README.pt.md: missing.md does not exist",
    ]


def test_a_missing_junit_flag_is_a_key_error(tmp_path):
    repository = _repository(tmp_path)

    with pytest.raises(KeyError, match="--junit"):
        check_readme_facts.main(["x", "--repo", str(repository)])


def test_a_trailing_flag_without_a_value_is_silently_dropped(tmp_path, capsys):
    repository = _repository(tmp_path)

    exit_code = check_readme_facts.main(
        ["x", "--junit", str(repository / "report.xml"), "--repo", str(repository), "--ignored"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("README facts and links OK")


def test_a_pyproject_without_the_coverage_gate_is_a_value_error(tmp_path):
    repository = _repository(tmp_path)
    (repository / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-q"\n')

    with pytest.raises(ValueError, match="no --cov-fail-under"):
        check_readme_facts.main(
            ["x", "--junit", str(repository / "report.xml"), "--repo", str(repository)]
        )


def test_a_missing_fact_file_is_a_file_not_found_error(tmp_path):
    repository = _repository(tmp_path)
    (repository / "guide/pt/index.md").unlink()

    with pytest.raises(FileNotFoundError, match=r"index\.md"):
        check_readme_facts.main(
            ["x", "--junit", str(repository / "report.xml"), "--repo", str(repository)]
        )


def test_link_targets_with_a_scheme_are_skipped_and_html_references_are_checked(tmp_path):
    repository = _repository(tmp_path)
    (repository / "README.md").write_text(
        GOOD_BLOCK + "[a](mailto:x@y.z) [b](https://x.test) [c](#nope)\n"
        '<a href="docs/gone.md">x</a> <img srcset="img/gone.png">\n'
    )

    assert check_readme_facts.link_problems(repository, "README.md") == [
        "README.md: #nope — no such anchor",
        "README.md: docs/gone.md does not exist",
        "README.md: img/gone.png does not exist",
    ]
