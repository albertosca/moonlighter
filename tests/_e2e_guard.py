"""pytest plugin: a skipped e2e test is a failure, never a quiet green.

An e2e test only runs when someone selected it (``addopts`` deselects the
marker), so a skip there means "you asked for the real thing and got nothing".
Loaded for the whole suite through ``addopts`` (``-p tests._e2e_guard``).
"""

from collections.abc import Generator

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.skipped and item.get_closest_marker("e2e") is not None:
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"e2e test skipped — explicitly selected, so this is a failure: {reason}"
    return report
