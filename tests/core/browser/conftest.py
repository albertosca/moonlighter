"""Every session test starts and ends with the browser module's three singletons cleared."""

import pytest
from moonlighter.core import browser


@pytest.fixture(autouse=True)
def reset_browser_globals():
    """Reset module-level singletons before each test."""
    browser._playwright = None
    browser._browser = None
    browser._browser_process = None
    yield
    browser._playwright = None
    browser._browser = None
    browser._browser_process = None
