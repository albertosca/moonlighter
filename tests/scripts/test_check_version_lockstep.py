import textwrap
from pathlib import Path

import check_version_lockstep


def _write_repo(root: Path, versions: dict[str, str], pins: dict[str, str]) -> None:
    """A minimal fake monorepo: packages/<slug>/pyproject.toml with a version,
    plus packages/full/pyproject.toml with the four ==pins."""
    for slug, version in versions.items():
        package_directory = root / "packages" / slug
        package_directory.mkdir(parents=True)
        (package_directory / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    deps = "\n".join(f'    "moonlighter-{slug}=={pin}",' for slug, pin in pins.items())
    (root / "packages" / "full" / "pyproject.toml").write_text(
        textwrap.dedent(f"""\
            [project]
            version = "{versions["full"]}"
            dependencies = [
            {deps}
            ]
            """)
    )


CONSISTENT = {"core": "0.2.0", "scan": "0.2.0", "apply": "0.2.0", "email": "0.2.0", "full": "0.2.0"}
CONSISTENT_PINS = {"core": "0.2.0", "scan": "0.2.0", "apply": "0.2.0", "email": "0.2.0"}


def test_consistent_versions_report_no_mismatches(tmp_path):
    _write_repo(tmp_path, CONSISTENT, CONSISTENT_PINS)
    assert check_version_lockstep.check(tmp_path) == []


def test_a_sibling_package_version_drifted_is_reported(tmp_path):
    # The canary: prove the script actually catches drift, not just passes by
    # construction. core bumped to 0.3.0 but nothing else moved.
    versions = {**CONSISTENT, "core": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    mismatches = check_version_lockstep.check(tmp_path)
    assert len(mismatches) == 1
    assert "core" in mismatches[0]
    assert "0.3.0" in mismatches[0]
    assert "0.2.0" in mismatches[0]


def test_a_pin_in_full_left_behind_is_reported(tmp_path):
    # The other half: every package version bumped together, but the pin in
    # moonlighter-full's own dependency list was forgotten.
    versions = {
        "core": "0.3.0",
        "scan": "0.3.0",
        "apply": "0.3.0",
        "email": "0.3.0",
        "full": "0.3.0",
    }
    pins = {**CONSISTENT_PINS, "apply": "0.2.0"}  # forgotten pin
    _write_repo(tmp_path, versions, pins)
    mismatches = check_version_lockstep.check(tmp_path)
    assert any("apply" in mismatch and "0.2.0" in mismatch for mismatch in mismatches)


def test_multiple_mismatches_are_all_reported(tmp_path):
    versions = {**CONSISTENT, "core": "0.3.0", "scan": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    mismatches = check_version_lockstep.check(tmp_path)
    assert len(mismatches) == 2


def test_main_exits_zero_when_consistent(tmp_path, capsys):
    _write_repo(tmp_path, CONSISTENT, CONSISTENT_PINS)
    assert check_version_lockstep.main(tmp_path) == 0
    assert "consistent" in capsys.readouterr().out.lower()


def test_main_exits_nonzero_and_names_the_drift(tmp_path, capsys):
    versions = {**CONSISTENT, "core": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    assert check_version_lockstep.main(tmp_path) != 0
    out = capsys.readouterr().out
    assert "core" in out
    assert "0.3.0" in out


def test_real_repo_is_currently_consistent():
    # The actual moonlighter monorepo, checked as-is — proves the script reads
    # real pyproject.toml files correctly, not just the synthetic fixture shape.
    repo_root = Path(__file__).resolve().parents[2]
    assert check_version_lockstep.check(repo_root) == []


def test_main_prints_the_exact_success_line(tmp_path, capsys):
    _write_repo(tmp_path, CONSISTENT, CONSISTENT_PINS)

    assert check_version_lockstep.main(tmp_path) == 0

    assert capsys.readouterr().out == "Version lockstep is consistent at 0.2.0.\n"


def test_main_prints_every_mismatch_under_one_header_and_returns_one(tmp_path, capsys):
    versions = {**CONSISTENT, "core": "0.3.0"}
    _write_repo(tmp_path, versions, {**CONSISTENT_PINS, "email": "0.1.0"})

    assert check_version_lockstep.main(tmp_path) == 1

    assert capsys.readouterr().out == (
        "Version lockstep broken:\n"
        "  - packages/core/pyproject.toml is at 0.3.0, expected 0.2.0 (to match moonlighter-full)\n"
        "  - packages/full/pyproject.toml pins moonlighter-email==0.1.0, expected ==0.2.0\n"
    )


def test_a_pin_missing_from_full_is_skipped_without_a_report(tmp_path):
    pins = {slug: pin for slug, pin in CONSISTENT_PINS.items() if slug != "scan"}
    _write_repo(tmp_path, CONSISTENT, pins)

    assert check_version_lockstep.check(tmp_path) == []
