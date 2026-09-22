"""An explicitly selected e2e test must never report a skip as success.

History: the browser e2e suite skipped itself into green for weeks (2026-08-03)
because a fixture found no browser and called ``pytest.skip`` — ``pytest -m e2e``
reported success having exercised nothing. The guard turns that skip into a
failure, for every e2e test, present and future.
"""

import pytest

pytest_plugins = ["pytester"]

_TEST_FILE = """
import pytest

@pytest.mark.e2e
def test_needs_a_tool():
    pytest.skip("tool not installed")

def test_ordinary_skip():
    pytest.skip("not relevant here")
"""


_INI = "[pytest]\nasyncio_default_fixture_loop_scope = function\nmarkers =\n    e2e: end-to-end\n"


def _run(pytester: pytest.Pytester, source: str) -> pytest.RunResult:
    pytester.makeini(_INI)
    pytester.makepyfile(source)
    return pytester.runpytest("-p", "tests._e2e_guard", "-p", "no:cacheprovider")


def test_a_skipped_e2e_test_fails(pytester: pytest.Pytester) -> None:
    result = _run(pytester, _TEST_FILE)
    result.assert_outcomes(failed=1, skipped=1)
    result.stdout.fnmatch_lines(["*e2e test skipped*tool not installed*"])


def test_a_passing_e2e_test_still_passes(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "import pytest\n\n@pytest.mark.e2e\ndef test_ok():\n    assert True\n")
    result.assert_outcomes(passed=1)


def test_the_guard_is_loaded_by_the_real_suite(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.pluginmanager.has_plugin("tests._e2e_guard")
