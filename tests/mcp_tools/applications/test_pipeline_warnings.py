"""get_pipeline lists the setup warnings only while there are some, and tells errors from warnings."""

import os
from unittest.mock import patch

from moonlighter.core.db import init_db
from moonlighter.mcp_tools.applications import get_pipeline

from tests._context import make_test_context


async def test_get_pipeline_shows_warnings_when_setup_incomplete(temporary_database):
    """An empty profile (the make_test_context default) surfaces a Setup Warnings
    section with a distinguishable marker, prepended before the pipeline itself.
    """
    init_db()

    result = await get_pipeline(context=make_test_context(profile={}))
    assert "# Setup Warnings" in result
    assert "[WARN]" in result or "[ERROR]" in result
    assert result.index("# Setup Warnings") < result.index("# Application Pipeline")


async def test_get_pipeline_no_warnings_section_when_setup_is_clean(temporary_database, tmp_path):
    """A fully-configured setup (real profile, real cv.pdf, cli backend, existing
    browser) produces zero warnings -> no Setup Warnings section at all, and the
    pipeline output is unchanged from the pre-existing behavior.
    """
    init_db()

    cv_path = tmp_path / "cv.pdf"
    cv_path.write_text("fake cv")
    browser = tmp_path / "browser"
    browser.write_text("fake browser")
    config = {"llm_backend": "cli", "browser_path": str(browser)}
    profile = {"skills": ["python"]}

    # `claude` must be pinned as present: the cli backend now checks for it, and
    # the dev machine has it while CI does not -- otherwise this passes locally
    # and fails in CI for a reason that has nothing to do with the assertion.
    with (
        patch("moonlighter.startup.moonlighter_home", return_value=tmp_path),
        patch("moonlighter.startup.shutil.which", return_value="/usr/local/bin/claude"),
    ):
        result = await get_pipeline(context=make_test_context(config=config, profile=profile))
    assert "# Setup Warnings" not in result
    assert result.startswith("# Application Pipeline")


async def test_get_pipeline_warnings_distinguish_error_and_warn_levels(
    temporary_database, tmp_path
):
    """No ANTHROPIC_API_KEY + api backend -> an 'error'-level warning; missing cv.pdf
    -> a 'warn'-level warning. Both render with their own marker in the same call.
    """
    init_db()

    with (
        patch("moonlighter.startup.moonlighter_home", return_value=tmp_path),
        patch.dict("os.environ", {}, clear=False),
    ):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        config = {"llm_backend": "api"}
        result = await get_pipeline(
            context=make_test_context(config=config, profile={"skills": []})
        )
    assert "[ERROR]" in result
    assert "[WARN]" in result
