from unittest.mock import patch

import pytest
from gauntler.application.appliers.ashby import AshbyApplier
from gauntler.application.appliers.greenhouse import GreenhouseApplier
from gauntler.application.appliers.lever import LeverApplier
from gauntler.application.appliers.linkedin import LinkedInApplier

# e2e suite: requires a real browser (launches Brave/Chromium). Outside the default run —
# run with `pytest -m e2e`. The coverage gate runs over the unit suite.
pytestmark = pytest.mark.e2e

# ── Greenhouse E2E ────────────────────────────────────────────────────────────


async def test_greenhouse_e2e_extract_fields(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/greenhouse_form.html")
    applier = GreenhouseApplier(page, {}, {})
    fields = await applier.extract_fields()
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
    fields = await applier.extract_fields()
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
    fields = await applier.extract_fields()
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


# ── LinkedIn E2E ──────────────────────────────────────────────────────────────


async def test_linkedin_e2e_is_easy_apply(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/linkedin_job.html")
    applier = LinkedInApplier(page, {}, {})
    result = await applier.is_easy_apply()
    assert result is True


async def test_linkedin_e2e_extract_fields_from_modal(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/linkedin_job.html")
    applier = LinkedInApplier(page, {}, {})
    with patch("asyncio.sleep"):
        fields = await applier.extract_fields()
    assert "Phone Number" in fields
    assert "Years of Experience" in fields


async def test_linkedin_e2e_fill_form(browser_page):
    page, base_url = browser_page
    await page.goto(f"{base_url}/linkedin_job.html")
    applier = LinkedInApplier(page, {}, {})
    # extract_fields clicks the Easy Apply button — do it first to open modal
    with patch("asyncio.sleep"):
        await applier.extract_fields()
        await applier.fill_form({"Phone Number": "555-1234"}, cv_path="")
    value = await page.eval_on_selector("#phone", "el => el.value")
    assert value == "555-1234"
