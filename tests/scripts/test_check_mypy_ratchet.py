"""The mypy ratchet over tests/: counts per file, fails on growth and on a stale baseline."""

import json
import subprocess

import check_mypy_ratchet as ratchet
import pytest

_TWO_FILES = (
    "tests/a/test_one.py:3: error: Item None has no attribute x  [union-attr]\n"
    "tests/a/test_one.py:9: note: Revealed type\n"
    "tests/a/test_one.py:12: error: Unsupported operand  [operator]\n"
    "tests/b/test_two.py:5: error: Argument 1 has incompatible type  [arg-type]\n"
    "Found 3 errors in 2 files (checked 4 source files)\n"
)


def _completed(stdout: str, returncode: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["mypy"], returncode, stdout=stdout, stderr="")


def test_errors_are_counted_per_file_and_notes_are_not():
    counts = ratchet.count_errors(_completed(_TWO_FILES, 1))
    assert counts == {"tests/a/test_one.py": 2, "tests/b/test_two.py": 1}


def test_a_clean_run_counts_nothing():
    clean = "Success: no issues found in 4 source files\n"
    assert ratchet.count_errors(_completed(clean, 0)) == {}


def test_a_summary_the_parser_does_not_match_fails_loudly():
    # A format change that the regex misses must not read as "no errors".
    unparsed = "tests/a/test_one.py:3:7: error: x  [union-attr]\nFound 1 error in 1 file\n"
    with pytest.raises(ratchet.RatchetError, match="parsed 0 of the 1 errors"):
        ratchet.count_errors(_completed(unparsed, 1))


def test_errors_without_a_summary_fail_loudly():
    with pytest.raises(ratchet.RatchetError, match="no summary line"):
        ratchet.count_errors(_completed("tests/a/test_one.py:3: error: x\n", 1))


def test_a_mypy_crash_is_not_a_clean_run():
    with pytest.raises(ratchet.RatchetError, match="exited with code 2"):
        ratchet.count_errors(_completed("", 2))


def test_a_file_above_its_baseline_is_reported():
    problems = ratchet.violations({"tests/a.py": 3}, {"tests/a.py": 2})
    assert problems == ["tests/a.py has 3 mypy errors; the baseline allows 2 — fix the new ones"]


def test_a_file_missing_from_the_baseline_may_have_none():
    problems = ratchet.violations({"tests/new.py": 1}, {})
    assert problems == ["tests/new.py has 1 mypy errors; the baseline allows 0 — fix the new ones"]


def test_a_file_below_its_baseline_asks_to_lock_the_gain():
    problems = ratchet.violations({"tests/a.py": 1}, {"tests/a.py": 2})
    assert problems == [
        "tests/a.py has 1 mypy errors, below the baseline's 2 — run with --update to lock it in"
    ]


def test_a_fixed_or_deleted_file_left_in_the_baseline_is_stale():
    problems = ratchet.violations({}, {"tests/gone.py": 4})
    assert problems == [
        "tests/gone.py has 0 mypy errors, below the baseline's 4 — run with --update to lock it in"
    ]


def test_matching_counts_report_nothing():
    assert ratchet.violations({"tests/a.py": 2}, {"tests/a.py": 2}) == []


def test_main_fails_on_growth_and_passes_on_match(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"tests/a/test_one.py": 1, "tests/b/test_two.py": 1}))
    monkeypatch.setattr(ratchet, "run_mypy", lambda: _completed(_TWO_FILES, 1))
    assert ratchet.main([], baseline_path=baseline) == 1
    assert "tests/a/test_one.py has 2 mypy errors" in capsys.readouterr().out

    baseline.write_text(json.dumps({"tests/a/test_one.py": 2, "tests/b/test_two.py": 1}))
    assert ratchet.main([], baseline_path=baseline) == 0


def test_main_update_rewrites_the_baseline_sorted(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}")
    monkeypatch.setattr(ratchet, "run_mypy", lambda: _completed(_TWO_FILES, 1))
    assert ratchet.main(["--update"], baseline_path=baseline) == 0
    assert json.loads(baseline.read_text()) == {
        "tests/a/test_one.py": 2,
        "tests/b/test_two.py": 1,
    }
    assert baseline.read_text().endswith("}\n")


def test_main_reports_a_crash_instead_of_passing(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}")
    monkeypatch.setattr(ratchet, "run_mypy", lambda: _completed("", 2))
    assert ratchet.main([], baseline_path=baseline) == 1
    assert "exited with code 2" in capsys.readouterr().out
