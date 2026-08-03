from unittest.mock import patch

import pytest
from moonlighter.application.appliers.ashby import AshbyApplier
from moonlighter.application.appliers.greenhouse import GreenhouseApplier
from moonlighter.application.appliers.lever import LeverApplier
from moonlighter.application.appliers.recruitee import RecruiteeApplier

# e2e suite: requires a real browser (launches Brave/Chromium). Outside the default run —
# run with `pytest -m e2e`. The coverage gate runs over the unit suite.
pytestmark = pytest.mark.e2e

# ── Greenhouse E2E ────────────────────────────────────────────────────────────


async def test_greenhouse_e2e_extract_fields(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/greenhouse_form.html")
    applier = GreenhouseApplier(page, {}, {})
    fields, _ = await applier.extract_fields()
    # Should have "Full Name" and "Email", but NOT "Resume/CV" or "Cover Letter"
    assert "Full Name" in fields
    assert "Email" in fields
    assert "Resume/CV" not in fields
    assert "Cover Letter" not in fields


async def test_greenhouse_e2e_fill_form(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/greenhouse_form.html")
    applier = GreenhouseApplier(page, {}, {})
    with patch("asyncio.sleep"):
        await applier.fill_form({"Full Name": "Alberto Cavalcanti"}, cv_path="")
    value = await page.eval_on_selector("#full_name", "el => el.value")
    assert value == "Alberto Cavalcanti"


async def test_greenhouse_e2e_submit(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/greenhouse_form.html")
    applier = GreenhouseApplier(page, {}, {})
    # submit() returns True when button is found and clicked
    result = await applier.submit()
    assert result == "submitted"


async def test_greenhouse_e2e_detect_false_for_local_url(browser_page):
    """Local file:// URL doesn't contain greenhouse.io → detect() returns False."""
    page, base_url = browser_page
    await page.goto(f"{base_url}/greenhouse_form.html")
    applier = GreenhouseApplier(page, {}, {})
    result = await applier.detect()
    assert result is False


# ── Lever E2E ─────────────────────────────────────────────────────────────────


async def test_lever_e2e_extract_fields(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/lever_form.html")
    applier = LeverApplier(page, {}, {})
    fields, _ = await applier.extract_fields()
    assert len(fields) > 0
    # At least some non-empty labels exist
    assert any(f.strip() for f in fields)


async def test_lever_e2e_fill_form(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/lever_form.html")
    applier = LeverApplier(page, {}, {})
    with patch("asyncio.sleep"):
        await applier.fill_form({"Name": "Alberto"}, cv_path="")
    value = await page.eval_on_selector("#lever_name", "el => el.value")
    assert value == "Alberto"


async def test_lever_e2e_submit(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/lever_form.html")
    applier = LeverApplier(page, {}, {})
    result = await applier.submit()
    assert result == "submitted"


# ── Ashby E2E ─────────────────────────────────────────────────────────────────


async def test_ashby_e2e_extract_fields(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/ashby_form.html")
    applier = AshbyApplier(page, {}, {})
    fields, _ = await applier.extract_fields()
    assert "Why this role?" in fields
    assert "Full Name" in fields


async def test_ashby_e2e_fill_form(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/ashby_form.html")
    applier = AshbyApplier(page, {}, {})
    with patch("asyncio.sleep"):
        await applier.fill_form({"Why this role?": "Excited about AI research"}, cv_path="")
    value = await page.eval_on_selector("#why_role", "el => el.value")
    assert value == "Excited about AI research"


async def test_ashby_e2e_submit(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/ashby_form.html")
    applier = AshbyApplier(page, {}, {})
    result = await applier.submit()
    assert result == "submitted"


# LinkedIn E2E tests moved to the private moonlighter-linkedin repo -- see
# docs/superpowers/specs/2026-07-22-linkedin-plugin-split-design.md.


# ── Recruitee E2E ─────────────────────────────────────────────────────────────


async def test_recruitee_e2e_radio_group_is_one_question(browser_page):
    """The radio-group discovery is JavaScript, so the unit tests mock it away
    and cannot catch a selector bug. They did not: `:scope`-less selectors made
    discovery return nothing on the real page while the mocked test stayed
    green. This exercises the actual JS against the real DOM shape."""
    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_form.html")
    applier = RecruiteeApplier(page, {}, {})

    groups = await applier._radio_groups()

    assert list(groups) == ["How do you rate your own skills with Node.js? *"]
    assert groups["How do you rate your own skills with Node.js? *"] == [
        "Beginner",
        "Intermediate",
        "Advanced",
    ]


async def test_recruitee_e2e_extract_fields_drops_the_options(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_form.html")
    applier = RecruiteeApplier(page, {}, {})

    fields, closed = await applier.extract_fields()

    assert "How do you rate your own skills with Node.js? *" in fields
    assert "How do you rate your own skills with Node.js? *" in closed
    for option in ("Beginner", "Intermediate", "Advanced"):
        assert option not in fields
    assert "Full name *" in fields


async def test_recruitee_e2e_fill_form_checks_the_radio(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_form.html")
    applier = RecruiteeApplier(page, {}, {})

    status = await applier.fill_form(
        {"How do you rate your own skills with Node.js? *": "Advanced: 9 years of Node.js"},
        cv_path="",
    )

    assert status["How do you rate your own skills with Node.js? *"] == "filled"
    assert await page.locator("#skill-2").is_checked()
    assert not await page.locator("#skill-0").is_checked()
