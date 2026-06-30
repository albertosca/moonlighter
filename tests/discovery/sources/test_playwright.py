from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def make_page(initial_url="https://www.linkedin.com/jobs/search/?keywords=engineer"):
    page = MagicMock()
    page.url = initial_url
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])
    return page


# ── session detection ─────────────────────────────────────────────────────────


async def test_linkedin_scanner_raises_on_login_redirect():
    """Após goto(), se page.url contém '/login', levanta LinkedInSessionExpiredError."""
    page = make_page()

    async def goto_side_effect(url, **kwargs):
        page.url = "https://www.linkedin.com/login?fromSignIn=true&trk=..."

    page.goto = AsyncMock(side_effect=goto_side_effect)

    from gauntler.discovery.sources.playwright import (
        LinkedInScanner,
        LinkedInSessionExpiredError,
    )

    scanner = LinkedInScanner(page)
    with pytest.raises(LinkedInSessionExpiredError):
        await scanner.scan(keywords="engineer")


async def test_linkedin_scanner_raises_on_checkpoint_redirect():
    """page.url contendo '/checkpoint' → LinkedInSessionExpiredError."""
    page = make_page()

    async def goto_side_effect(url, **kwargs):
        page.url = "https://www.linkedin.com/checkpoint/challenge/abc123"

    page.goto = AsyncMock(side_effect=goto_side_effect)

    from gauntler.discovery.sources.playwright import (
        LinkedInScanner,
        LinkedInSessionExpiredError,
    )

    scanner = LinkedInScanner(page)
    with pytest.raises(LinkedInSessionExpiredError):
        await scanner.scan(keywords="engineer")


async def test_linkedin_scanner_raises_on_authwall():
    """page.url contendo '/authwall' → LinkedInSessionExpiredError."""
    page = make_page()

    async def goto_side_effect(url, **kwargs):
        page.url = "https://www.linkedin.com/authwall?trk=..."

    page.goto = AsyncMock(side_effect=goto_side_effect)

    from gauntler.discovery.sources.playwright import (
        LinkedInScanner,
        LinkedInSessionExpiredError,
    )

    scanner = LinkedInScanner(page)
    with pytest.raises(LinkedInSessionExpiredError):
        await scanner.scan(keywords="engineer")


async def test_linkedin_scanner_valid_session_no_exception():
    """URL válida de resultados de busca → sem exceção."""
    page = make_page(initial_url="https://www.linkedin.com/jobs/search/?keywords=engineer")
    page.wait_for_selector = AsyncMock(side_effect=Exception("no results"))  # timeout ok

    from gauntler.discovery.sources.playwright import LinkedInScanner

    scanner = LinkedInScanner(page)
    # Não lança LinkedInSessionExpiredError, pode lançar outra coisa
    try:
        await scanner.scan(keywords="engineer")
    except Exception as e:
        assert "session" not in str(e).lower() and "login" not in str(e).lower()


async def test_linkedin_scanner_returns_jobs_on_success():
    """Sessão válida + resultados encontrados → lista de RawJobs."""
    page = make_page()

    title_el = MagicMock()
    title_el.inner_text = AsyncMock(return_value="Senior Engineer")
    company_el = MagicMock()
    company_el.inner_text = AsyncMock(return_value="Stripe")
    link_el = MagicMock()
    link_el.get_attribute = AsyncMock(return_value="https://www.linkedin.com/jobs/view/123?trk=abc")
    location_el = MagicMock()
    location_el.inner_text = AsyncMock(return_value="Remote")

    listing = MagicMock()
    listing.query_selector = AsyncMock(
        side_effect=lambda sel: {
            ".base-search-card__title": title_el,
            ".base-search-card__subtitle": company_el,
            "a.base-card__full-link": link_el,
            ".job-search-card__location": location_el,
        }.get(sel)
    )

    page.query_selector_all = AsyncMock(return_value=[listing])

    with patch("asyncio.sleep", new=AsyncMock()):
        from gauntler.discovery.sources.playwright import LinkedInScanner

        scanner = LinkedInScanner(page)
        with patch.object(LinkedInScanner, "_fetch_description", new=AsyncMock(return_value=None)):
            jobs = await scanner.scan(keywords="engineer")

    assert len(jobs) == 1
    assert jobs[0].title == "Senior Engineer"
    assert jobs[0].company == "Stripe"
    assert "?trk=" not in jobs[0].url  # tracking params removed


# ── _fetch_description ────────────────────────────────────────────────────────


class TestFetchDescription:
    def _make_scanner(self):
        page = make_page()
        from gauntler.discovery.sources.playwright import LinkedInScanner

        return LinkedInScanner(page), page

    async def test_returns_description_when_panel_loads(self):
        scanner, page = self._make_scanner()
        card = MagicMock()
        card.click = AsyncMock()

        desc_el = MagicMock()
        desc_el.inner_text = AsyncMock(return_value="  We are building payments infra.  ")
        page.wait_for_selector = AsyncMock(return_value=desc_el)

        result = await scanner._fetch_description(card)
        assert result == "We are building payments infra."
        card.click.assert_called_once()

    async def test_returns_none_when_panel_times_out(self):
        scanner, page = self._make_scanner()
        card = MagicMock()
        card.click = AsyncMock()

        from playwright.async_api import TimeoutError as PlaywrightTimeout

        page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeout("timeout"))

        result = await scanner._fetch_description(card)
        assert result is None

    async def test_returns_none_when_desc_element_not_found(self):
        scanner, page = self._make_scanner()
        card = MagicMock()
        card.click = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)

        result = await scanner._fetch_description(card)
        assert result is None

    async def test_returns_none_when_desc_text_is_empty(self):
        scanner, page = self._make_scanner()
        card = MagicMock()
        card.click = AsyncMock()

        desc_el = MagicMock()
        desc_el.inner_text = AsyncMock(return_value="   ")
        page.wait_for_selector = AsyncMock(return_value=desc_el)

        result = await scanner._fetch_description(card)
        assert result is None

    async def test_returns_none_when_click_raises(self):
        scanner, _page = self._make_scanner()
        card = MagicMock()
        card.click = AsyncMock(side_effect=Exception("element detached"))

        result = await scanner._fetch_description(card)
        assert result is None

    async def test_description_populated_in_scan_result(self):
        """Quando _fetch_description retorna texto, RawJob.description é preenchido."""
        page = make_page()

        title_el = MagicMock()
        title_el.inner_text = AsyncMock(return_value="Backend Engineer")
        company_el = MagicMock()
        company_el.inner_text = AsyncMock(return_value="Nubank")
        link_el = MagicMock()
        link_el.get_attribute = AsyncMock(return_value="https://www.linkedin.com/jobs/view/999")
        location_el = MagicMock()
        location_el.inner_text = AsyncMock(return_value="Remote")

        listing = MagicMock()
        listing.query_selector = AsyncMock(
            side_effect=lambda sel: {
                ".base-search-card__title": title_el,
                ".base-search-card__subtitle": company_el,
                "a.base-card__full-link": link_el,
                ".job-search-card__location": location_el,
            }.get(sel)
        )
        page.query_selector_all = AsyncMock(return_value=[listing])

        with patch("asyncio.sleep", new=AsyncMock()):
            from gauntler.discovery.sources.playwright import LinkedInScanner

            scanner = LinkedInScanner(page)
            with patch.object(
                LinkedInScanner,
                "_fetch_description",
                new=AsyncMock(return_value="Build Pix infra at Nubank."),
            ):
                jobs = await scanner.scan(keywords="engineer")

        assert len(jobs) == 1
        assert jobs[0].description == "Build Pix infra at Nubank."


@pytest.mark.asyncio
async def test_linkedin_scanner_logs_start_and_found(caplog):
    import logging

    from gauntler.discovery.sources.playwright import LinkedInScanner

    page = AsyncMock()
    page.url = "https://www.linkedin.com/jobs/search/?keywords=eng"
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])  # 0 results

    scanner = LinkedInScanner(page)
    with caplog.at_level(logging.INFO, logger="gauntler.discovery.sources.playwright"):
        await scanner.scan(keywords="eng")

    assert "LinkedIn scan: starting" in caplog.text
    assert "LinkedIn: found" in caplog.text
