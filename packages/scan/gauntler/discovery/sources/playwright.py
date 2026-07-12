import asyncio
from typing import Any

from gauntler.core.log import get_logger
from gauntler.discovery.sources.base import BaseScanner, RawJob, normalize_remote_type
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

logger = get_logger(__name__)

_DESCRIPTION_SELECTORS = ".jobs-description-content__text, .show-more-less-html__markup"
_LOGIN_REDIRECTS = ("/login", "/checkpoint", "/authwall")


class LinkedInSessionExpiredError(Exception):
    """Levantada quando o LinkedIn redireciona para login após goto()."""

    pass


async def _text(el: Any) -> str:
    if not el:
        return ""
    text: str = (await el.inner_text()).strip()
    return text


class LinkedInScanner(BaseScanner):
    SEARCH_URL = (
        "https://www.linkedin.com/jobs/search/?"
        "keywords={keywords}&location={location}&f_WT=2&sortBy=DD"
    )
    # f_WT=2 = Remote filter

    def __init__(self, page: Page):
        self.page = page

    async def scan(
        self,
        company_slugs: list[str] | None = None,
        keywords: str = "",
        location: str = "Worldwide",
        **kwargs: Any,
    ) -> list[RawJob]:
        url = self.SEARCH_URL.format(
            keywords=keywords.replace(" ", "%20") or "software+engineer",
            location=location.replace(" ", "%20"),
        )
        logger.info("LinkedIn scan: starting (keywords=%r)", keywords or "software engineer")
        if not await self._load_results(url):
            return []

        listings = await self.page.query_selector_all(".jobs-search__results-list > li")
        jobs = []
        for item in listings[:30]:  # cap em 30 por busca
            job = await self._parse_listing(item)
            if job:
                jobs.append(job)
        logger.info("LinkedIn: found %d jobs", len(jobs))
        return jobs

    async def _load_results(self, url: str) -> bool:
        """Abre a busca, detecta sessão expirada e espera a lista carregar (com scroll
        para o lazy-load). False se a lista não apareceu (timeout)."""
        try:
            await self.page.goto(url, timeout=30000)
            if any(marker in self.page.url for marker in _LOGIN_REDIRECTS):
                raise LinkedInSessionExpiredError(
                    "Sessão LinkedIn expirada. Execute login(platform='linkedin') para re-autenticar."
                )
            await self.page.wait_for_selector(".jobs-search__results-list", timeout=15000)
        except LinkedInSessionExpiredError:
            raise  # propaga sem engolir
        except PlaywrightTimeout:
            logger.warning("LinkedIn scan: timeout aguardando resultados")
            return False

        for _ in range(3):  # LinkedIn faz lazy-load — rola para carregar mais
            await self.page.keyboard.press("End")
            await asyncio.sleep(1.5)
        return True

    async def _parse_listing(self, item: Any) -> RawJob | None:
        """Extrai um RawJob de um card da lista. None se o card estiver incompleto
        ou der erro."""
        try:
            title = await _text(await item.query_selector(".base-search-card__title"))
            company = await _text(await item.query_selector(".base-search-card__subtitle"))
            location_text = await _text(await item.query_selector(".job-search-card__location"))
            link_el = await item.query_selector("a.base-card__full-link")
            url_val = await link_el.get_attribute("href") if link_el else ""
            if not title or not url_val:
                return None

            return RawJob(
                source="linkedin",
                company=company,
                title=title,
                url=url_val.split("?")[0],  # remove tracking params
                location=location_text,
                remote_type=normalize_remote_type(location_text) or "remote",
                description=await self._fetch_description(item),
            )
        except Exception:
            return None

    async def _fetch_description(self, card_item: Any) -> str | None:
        """Clica no card e extrai a descrição do painel lateral. Retorna None se falhar."""
        try:
            await card_item.click()
            desc_el = await self.page.wait_for_selector(_DESCRIPTION_SELECTORS, timeout=5000)
            if desc_el:
                text = (await desc_el.inner_text()).strip()
                return text or None
        except Exception as e:
            logger.debug("description fetch failed: %s", e)
        return None
