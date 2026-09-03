import sys
import textwrap
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _cvl():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import check_version_lockstep

    return check_version_lockstep


def _write_repo(root: Path, versions: dict[str, str], pins: dict[str, str]) -> None:
    """A minimal fake monorepo: packages/<slug>/pyproject.toml with a version,
    plus packages/full/pyproject.toml with the four ==pins."""
    for slug, version in versions.items():
        pkg_dir = root / "packages" / slug
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
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
    cvl = _cvl()
    assert cvl.check(tmp_path) == []


def test_a_sibling_package_version_drifted_is_reported(tmp_path):
    # The canary: prove the script actually catches drift, not just passes by
    # construction. core bumped to 0.3.0 but nothing else moved.
    versions = {**CONSISTENT, "core": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    cvl = _cvl()
    mismatches = cvl.check(tmp_path)
    assert len(mismatches) == 1
    assert "core" in mismatches[0] and "0.3.0" in mismatches[0] and "0.2.0" in mismatches[0]


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
    cvl = _cvl()
    mismatches = cvl.check(tmp_path)
    assert any("apply" in m and "0.2.0" in m for m in mismatches)


def test_multiple_mismatches_are_all_reported(tmp_path):
    versions = {**CONSISTENT, "core": "0.3.0", "scan": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    cvl = _cvl()
    mismatches = cvl.check(tmp_path)
    assert len(mismatches) == 2


def test_main_exits_zero_when_consistent(tmp_path, capsys):
    _write_repo(tmp_path, CONSISTENT, CONSISTENT_PINS)
    cvl = _cvl()
    assert cvl.main(tmp_path) == 0
    assert "consistent" in capsys.readouterr().out.lower()


def test_main_exits_nonzero_and_names_the_drift(tmp_path, capsys):
    versions = {**CONSISTENT, "core": "0.3.0"}
    _write_repo(tmp_path, versions, CONSISTENT_PINS)
    cvl = _cvl()
    assert cvl.main(tmp_path) != 0
    out = capsys.readouterr().out
    assert "core" in out and "0.3.0" in out


def test_real_repo_is_currently_consistent():
    # The actual moonlighter monorepo, checked as-is — proves the script reads
    # real pyproject.toml files correctly, not just the synthetic fixture shape.
    repo_root = Path(__file__).resolve().parents[2]
    cvl = _cvl()
    assert cvl.check(repo_root) == []
