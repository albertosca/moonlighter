import asyncio
from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from candidatador.scanner.base import BaseScanner, RawJob, normalize_remote_type


class LinkedInSessionExpiredError(Exception):
    """Levantada quando o LinkedIn redireciona para login após goto()."""
    pass


class LinkedInScanner(BaseScanner):
    SEARCH_URL = (
        "https://www.linkedin.com/jobs/search/?"
        "keywords={keywords}&location={location}&f_WT=2&sortBy=DD"
    )
    # f_WT=2 = Remote filter

    def __init__(self, page: Page):
        self.page = page

    async def scan(self, company_slugs: list[str] = None, keywords: str = "", location: str = "Worldwide", **kwargs) -> list[RawJob]:
        url = self.SEARCH_URL.format(
            keywords=keywords.replace(" ", "%20") or "software+engineer",
            location=location.replace(" ", "%20"),
        )
        jobs = []
        try:
            await self.page.goto(url, timeout=30000)
            redirect_markers = ("/login", "/checkpoint", "/authwall")
            if any(marker in self.page.url for marker in redirect_markers):
                raise LinkedInSessionExpiredError(
                    "Sessão LinkedIn expirada. Execute login(platform='linkedin') para re-autenticar."
                )
            await self.page.wait_for_selector(".jobs-search__results-list", timeout=15000)
        except LinkedInSessionExpiredError:
            raise  # propaga sem engolir
        except PlaywrightTimeout:
            return []

        # Scroll to load more results (LinkedIn lazy-loads)
        for _ in range(3):
            await self.page.keyboard.press("End")
            await asyncio.sleep(1.5)

        listings = await self.page.query_selector_all(".jobs-search__results-list > li")
        for item in listings[:30]:  # cap at 30 per search
            try:
                title_el = await item.query_selector(".base-search-card__title")
                company_el = await item.query_selector(".base-search-card__subtitle")
                link_el = await item.query_selector("a.base-card__full-link")
                location_el = await item.query_selector(".job-search-card__location")

                title = (await title_el.inner_text()).strip() if title_el else ""
                company = (await company_el.inner_text()).strip() if company_el else ""
                url_val = await link_el.get_attribute("href") if link_el else ""
                location_text = (await location_el.inner_text()).strip() if location_el else ""

                if not title or not url_val:
                    continue

                # Clean URL (remove tracking params)
                url_val = url_val.split("?")[0]

                jobs.append(RawJob(
                    source="linkedin",
                    company=company,
                    title=title,
                    url=url_val,
                    location=location_text,
                    remote_type=normalize_remote_type(location_text) or "remote",
                ))
            except Exception:
                continue

        return jobs
