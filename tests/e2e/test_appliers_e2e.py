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
    # The key carries a non-breaking space before the asterisk — never retype it.
    group = groups[next(iter(groups))]
    assert group["options"] == ["Beginner", "Intermediate", "Advanced"]
    assert group["name"] == "skill", "o grupo carrega o `name` que o identifica no DOM"


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


async def test_recruitee_e2e_submit_waits_for_the_spinner(browser_page):
    """The whole point of the wait: without it, classify runs while the button is
    still spinning and calls a successful submit a validation failure."""
    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_submit.html")
    await page.fill("#name", "Alberto")
    applier = RecruiteeApplier(page, {}, {})

    outcome = await applier.submit()

    assert outcome == "submitted", f"esperava submitted, veio {outcome!r}"
    assert not await page.locator("#done").is_hidden()


async def test_recruitee_e2e_detects_the_cdn_proxied_hcaptcha(browser_page):
    """Recruitee serves hCaptcha from captcha-assets.recruiteecdn.com, so a check
    for "hcaptcha.com" finds nothing. Matching the widget name is what works."""
    from moonlighter.application.appliers.base import detect_captcha

    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_submit.html")

    assert await detect_captcha(page) == "hcaptcha"


async def test_recruitee_e2e_reports_no_captcha_on_a_plain_form(browser_page):
    from moonlighter.application.appliers.base import detect_captcha

    page, base_url = browser_page
    await page.goto(f"{base_url}/recruitee_form.html")

    assert await detect_captcha(page) is None


# ── Workable E2E ──────────────────────────────────────────────────────────────


async def test_workable_e2e_each_screening_question_is_its_own_field(browser_page):
    """Four screening questions all labelled YES/NO collapsed into two dict keys
    and vanished from the draft. Keyed by the radio group's `name`, they survive."""
    from moonlighter.application.appliers.workable import WorkableApplier

    page, base_url = browser_page
    await page.goto(f"{base_url}/workable_form.html")
    applier = WorkableApplier(page, {}, {})

    fields, closed = await applier.extract_fields()

    questions = [f for f in fields if f.startswith(("Do you have", "Expertise"))]
    assert len(questions) == 2, f"esperava 2 perguntas distintas, veio {questions}"
    assert "YES" not in fields and "NO" not in fields
    assert all(q in closed for q in questions)


async def test_workable_e2e_answers_the_right_question(browser_page):
    """YES exists under both questions, so the wrong scoping silently answers the
    wrong one — which nothing downstream would catch."""
    from moonlighter.application.appliers.workable import WorkableApplier

    page, base_url = browser_page
    await page.goto(f"{base_url}/workable_form.html")
    applier = WorkableApplier(page, {}, {})

    status = await applier.fill_form(
        {"Expertise in building large React applications with TypeScript": "Yes"}, cv_path=""
    )

    assert status["Expertise in building large React applications with TypeScript"] == "filled"
    assert await page.locator("#q2y").is_checked()
    assert not await page.locator("#rXk3").is_checked(), "respondeu a pergunta errada"


async def test_workable_e2e_answers_an_aria_hidden_radio(browser_page):
    """Workable's real input is aria-hidden with a random id and no label[for];
    forcing a click on it answers "Clicking the checkbox did not change its
    state". The wrapping label is what a human clicks."""
    from moonlighter.application.appliers.workable import WorkableApplier

    page, base_url = browser_page
    await page.goto(f"{base_url}/workable_form.html")
    applier = WorkableApplier(page, {}, {})

    question = "Do you have at least 8 years of professional experience in software development?"
    status = await applier.fill_form({question: "Yes"}, cv_path="")

    assert status[question] == "filled"
    assert await page.locator("#rXk3").is_checked()
    assert not await page.locator("#rQ7z").is_checked()


async def test_workable_e2e_fills_a_field_whose_label_wraps_the_input(browser_page):
    """No `for`, a newline in the label text, and the required marker on its own
    line — the combination that made every text field not_found."""
    from moonlighter.application.appliers.workable import WorkableApplier

    page, base_url = browser_page
    await page.goto(f"{base_url}/workable_form.html")
    applier = WorkableApplier(page, {}, {})

    status = await applier.fill_form({"*\nFirst name": "Alberto"}, cv_path="")

    assert status["*\nFirst name"] == "filled", status
    assert await page.locator("#fn").input_value() == "Alberto"
