import check_readme_facts


def _facts(*, tests=1777, coverage=100, packages=5, branch_coverage=True, mypy_strict=True):
    return check_readme_facts.Facts(
        tests=tests,
        coverage=coverage,
        packages=packages,
        branch_coverage=branch_coverage,
        mypy_strict=mypy_strict,
    )


def _block(text: str) -> str:
    return f"intro\n<!-- facts -->{text}<!-- /facts -->\n"


def test_true_facts_pass():
    text = _block(
        "1,700+ tests · 100% branch coverage (CI-gated) · 5 packages on PyPI · mypy strict"
    )
    assert check_readme_facts.fact_problems("README.md", text, _facts()) == []


def test_portuguese_thousands_separator_parses():
    text = _block("1.700+ testes · 100% de cobertura de branches · 5 pacotes no PyPI")
    assert check_readme_facts.fact_problems("README.pt.md", text, _facts()) == []


def test_a_test_count_above_reality_is_a_false_claim():
    [problem] = check_readme_facts.fact_problems(
        "README.md", _block("1,800+ tests · 100% · 5 packages"), _facts()
    )
    assert "false" in problem
    assert "1800" in problem
    assert "1777" in problem


def test_a_test_count_trailing_by_more_than_the_band_is_stale():
    [problem] = check_readme_facts.fact_problems(
        "README.md", _block("1,500+ tests · 100% · 5 packages"), _facts()
    )
    assert "stale" in problem


def test_exactly_the_band_is_still_fine():
    assert (
        check_readme_facts.fact_problems(
            "README.md", _block("1,577+ tests · 100% · 5 packages"), _facts()
        )
        == []
    )


def test_coverage_and_package_mismatches_are_reported():
    problems = check_readme_facts.fact_problems(
        "README.md", _block("1,700+ tests · 95% · 4 packages"), _facts()
    )
    assert len(problems) == 2


def test_missing_or_duplicated_block_fails_instead_of_passing_vacuously():
    assert check_readme_facts.fact_problems("README.md", "no block here", _facts()) == [
        "README.md: expected exactly one facts block, found 0"
    ]
    two = _block("1,700+ tests · 100% · 5 packages") * 2
    assert check_readme_facts.fact_problems("README.md", two, _facts()) == [
        "README.md: expected exactly one facts block, found 2"
    ]


def test_a_branch_coverage_claim_needs_branch_coverage_on():
    text = _block("1,700+ tests · 100% branch coverage (CI-gated) · 5 packages")
    [problem] = check_readme_facts.fact_problems("README.md", text, _facts(branch_coverage=False))
    assert "branch" in problem


def test_the_portuguese_branch_claim_is_checked_too():
    text = _block("1.700+ testes · 100% de cobertura de branches · 5 pacotes")
    [problem] = check_readme_facts.fact_problems(
        "README.pt.md", text, _facts(branch_coverage=False)
    )
    assert "branch" in problem


def test_a_mypy_strict_claim_needs_strict_mypy():
    text = _block("1,700+ tests · 100% · 5 packages · mypy strict")
    [problem] = check_readme_facts.fact_problems("README.md", text, _facts(mypy_strict=False))
    assert "mypy" in problem


def test_facts_not_claimed_are_not_required():
    text = _block("1,700+ tests · 100% · 5 packages")
    assert (
        check_readme_facts.fact_problems(
            "README.md", text, _facts(branch_coverage=False, mypy_strict=False)
        )
        == []
    )


def test_a_block_missing_one_fact_is_reported():
    [problem] = check_readme_facts.fact_problems("README.md", _block("100% · 5 packages"), _facts())
    assert "test count" in problem


def test_junit_sums_every_suite_and_tolerates_missing_skipped(tmp_path):
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuites><testsuite tests="10" skipped="2"/><testsuite tests="5"/></testsuites>'
    )
    assert check_readme_facts.junit_test_count(report) == 13
    report.write_text('<testsuite tests="7" skipped="1"/>')
    assert check_readme_facts.junit_test_count(report) == 6


def test_real_facts_read_the_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = \"--cov --cov-fail-under=100 -m 'not e2e'\"\n"
    )
    for slug in ("core", "scan"):
        (tmp_path / "packages" / slug).mkdir(parents=True)
        (tmp_path / "packages" / slug / "pyproject.toml").write_text("")
    report = tmp_path / "r.xml"
    report.write_text('<testsuite tests="3"/>')
    assert check_readme_facts.real_facts(tmp_path, report) == _facts(
        tests=3, coverage=100, packages=2, branch_coverage=False, mypy_strict=False
    )


def test_real_facts_read_branch_coverage_and_strict_mypy(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=100"\n'
        "[tool.coverage.run]\nbranch = true\n"
        "[tool.mypy]\nstrict = true\n"
    )
    report = tmp_path / "r.xml"
    report.write_text('<testsuite tests="3"/>')
    facts = check_readme_facts.real_facts(tmp_path, report)
    assert facts.branch_coverage
    assert facts.mypy_strict


def test_one_files_problems_come_in_the_order_tests_coverage_packages_branch_mypy():
    text = _block("1,800+ tests · 95% branch coverage · 4 packages · mypy strict")

    problems = check_readme_facts.fact_problems(
        "README.md", text, _facts(branch_coverage=False, mypy_strict=False)
    )

    assert problems == [
        "README.md: claims 1800+ tests but there are 1777 — a false claim",
        "README.md: coverage must read 100% (the CI gate)",
        "README.md: package count must read 5",
        "README.md: claims branch coverage but [tool.coverage.run] branch is off",
        "README.md: claims mypy strict but [tool.mypy] strict is off",
    ]
