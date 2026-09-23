import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
REAL = None


def _crf():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import check_readme_facts

    return check_readme_facts


def _facts(tests=1777, coverage=100, packages=5):
    return _crf().Facts(tests=tests, coverage=coverage, packages=packages)


def _block(text: str) -> str:
    return f"intro\n<!-- facts -->{text}<!-- /facts -->\n"


def test_true_facts_pass():
    text = _block(
        "1,700+ tests · 100% branch coverage (CI-gated) · 5 packages on PyPI · mypy strict"
    )
    assert _crf().fact_problems("README.md", text, _facts()) == []


def test_portuguese_thousands_separator_parses():
    text = _block("1.700+ testes · 100% de cobertura de branches · 5 pacotes no PyPI")
    assert _crf().fact_problems("README.pt.md", text, _facts()) == []


def test_a_test_count_above_reality_is_a_false_claim():
    [problem] = _crf().fact_problems(
        "README.md", _block("1,800+ tests · 100% · 5 packages"), _facts()
    )
    assert "false" in problem and "1800" in problem and "1777" in problem


def test_a_test_count_trailing_by_more_than_the_band_is_stale():
    [problem] = _crf().fact_problems(
        "README.md", _block("1,500+ tests · 100% · 5 packages"), _facts()
    )
    assert "stale" in problem


def test_exactly_the_band_is_still_fine():
    assert (
        _crf().fact_problems("README.md", _block("1,577+ tests · 100% · 5 packages"), _facts())
        == []
    )


def test_coverage_and_package_mismatches_are_reported():
    problems = _crf().fact_problems(
        "README.md", _block("1,700+ tests · 95% · 4 packages"), _facts()
    )
    assert len(problems) == 2


def test_missing_or_duplicated_block_fails_instead_of_passing_vacuously():
    assert _crf().fact_problems("README.md", "no block here", _facts()) == [
        "README.md: expected exactly one facts block, found 0"
    ]
    two = _block("1,700+ tests · 100% · 5 packages") * 2
    assert _crf().fact_problems("README.md", two, _facts()) == [
        "README.md: expected exactly one facts block, found 2"
    ]


def test_a_block_missing_one_fact_is_reported():
    [problem] = _crf().fact_problems("README.md", _block("100% · 5 packages"), _facts())
    assert "test count" in problem


def test_junit_sums_every_suite_and_tolerates_missing_skipped(tmp_path):
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuites><testsuite tests="10" skipped="2"/><testsuite tests="5"/></testsuites>'
    )
    assert _crf().junit_test_count(report) == 13
    report.write_text('<testsuite tests="7" skipped="1"/>')
    assert _crf().junit_test_count(report) == 6


def test_real_facts_read_the_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = \"--cov --cov-fail-under=100 -m 'not e2e'\"\n"
    )
    for slug in ("core", "scan"):
        (tmp_path / "packages" / slug).mkdir(parents=True)
        (tmp_path / "packages" / slug / "pyproject.toml").write_text("")
    report = tmp_path / "r.xml"
    report.write_text('<testsuite tests="3"/>')
    assert _crf().real_facts(tmp_path, report) == _facts(tests=3, coverage=100, packages=2)


def test_slug_follows_github_rules():
    slug = _crf().slug
    assert slug("Extensions (adding a new ATS scanner)") == "extensions-adding-a-new-ats-scanner"
    assert slug("Instalação") == "instalação"
    assert slug("`moonlighter-scan` doctor") == "moonlighter-scan-doctor"
    assert slug("Sixty seconds of it") == "sixty-seconds-of-it"


def test_duplicate_headings_get_numbered_slugs():
    assert _crf().anchors("# Setup\n\n## Setup\n\n## Setup\n") == {"setup", "setup-1", "setup-2"}


def test_anchor_ignores_headings_in_code_fences():
    assert _crf().anchors("## Real\n\n```sh\n# not-a-heading\n```\n") == {"real"}


def test_link_problems_find_dead_files_and_anchors(tmp_path):
    (tmp_path / "guide").mkdir()
    (tmp_path / "guide/page.md").write_text("## Target\n")
    (tmp_path / "README.md").write_text(
        "[ok](guide/page.md#target) [bad-anchor](guide/page.md#nope) [gone](missing.md) "
        '[self](#local) [web](https://example.com) <img src="assets/x.svg">\n\n## Local\n'
    )
    problems = _crf().link_problems(tmp_path, "README.md")
    assert sorted(problems) == [
        "README.md: assets/x.svg does not exist",
        "README.md: guide/page.md#nope — no such anchor",
        "README.md: missing.md does not exist",
    ]
