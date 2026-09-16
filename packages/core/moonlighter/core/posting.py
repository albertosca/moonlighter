"""ATS-API routing for pasted job URLs.

add_job's generic HTTP fetch cannot read SPA pages (job #2646 stored a
styled-components CSS bundle as its description and got a meaningless score).
When the pasted URL matches a known ATS shape, the ATS's public API is the
reliable reader — and it also supplies company and title for free.
"""

import html
import re
from dataclasses import dataclass

import httpx
from moonlighter.core.http import HEADERS, FetchError, get_json
from moonlighter.core.urls import normalize_job_url

_GREENHOUSE_URL = re.compile(r"greenhouse\.io/(?P<board>[^/]+)/jobs/(?P<job_id>\d+)")
# Any host with a Recruitee-shaped /o/{offer} path: subdomain customers AND
# custom career domains (jobs.channable.com) serve the same /api/offers/ API
# (live-verified 2026-08-12). A non-Recruitee host with this path shape simply
# fails the API call and falls through to the generic fetch.
_OFFER_URL = re.compile(r"https?://(?P<host>[^/]+)/o/(?P<offer>[\w-]+)")

_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"


@dataclass
class FetchedPosting:
    company: str | None
    title: str | None
    description: str | None


def _strip_tags(raw: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip() or None


async def fetch_posting_via_ats(url: str) -> FetchedPosting | None:
    """Fetch a posting through its ATS's public API. None when the URL matches
    no known ATS or the API call fails — the caller falls back to the generic
    HTTP fetch."""
    if match := _GREENHOUSE_URL.search(url):
        return await _fetch_greenhouse(match["board"], match["job_id"])
    if match := _OFFER_URL.match(url):
        return await _fetch_recruitee_offer(match["host"], match["offer"])
    return None


async def _fetch_greenhouse(board: str, job_id: str) -> FetchedPosting | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            data = await get_json(client, _GREENHOUSE_API.format(board=board, job_id=job_id))
    except FetchError:
        return None
    if not isinstance(data, dict):
        return None
    # The board API returns `content` HTML-entity-escaped (&lt;div&gt;…).
    raw = html.unescape(data.get("content") or "")
    return FetchedPosting(
        company=data.get("company_name") or board,
        title=data.get("title"),
        description=_strip_tags(raw),
    )


async def _fetch_recruitee_offer(host: str, offer: str) -> FetchedPosting | None:
    """Fetches the whole offers feed and picks the matching entry.

    The single-offer endpoint (GET /api/offers/{offer}) would avoid the
    matching below entirely, and is the same API shape already live-verified
    (2026-08-11) in application/assisted/sources/recruitee.py -- but that
    verification only covers <slug>.recruitee.com hosts. This module deliberately
    also matches custom career domains (jobs.channable.com), and the list feed
    (/api/offers/) is what's actually live-verified (2026-08-12, see module
    docstring) to work across those. Switching to the single-offer endpoint here
    would be an unverified assumption for the custom-domain case, so instead
    the matching is fixed to be anchored: `needle` must match a full path
    segment, not merely be a substring, so `/o/backend-engineer` no longer
    matches `/o/backend-engineer-senior`.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            data = await get_json(client, f"https://{host}/api/offers/")
    except FetchError:
        return None
    if not isinstance(data, dict):
        return None
    needle = f"/o/{offer}"
    for item in data.get("offers") or []:
        apply_url = item.get("careers_apply_url") or ""
        if normalize_job_url(apply_url).endswith(needle):
            return FetchedPosting(
                company=item.get("company_name"),
                title=item.get("title"),
                description=_strip_tags(item.get("description") or ""),
            )
    return None


async def fetch_description(url: str) -> tuple[str | None, str | None]:
    """Fetches and cleans (strips HTML from) the job description. Returns (description,
    error) — only one of the two is non-null. Doesn't work on pages that require login."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=HEADERS)
        if r.status_code != 200:
            return None, (
                f"Could not fetch the URL (HTTP {r.status_code}). Provide 'description' manually."
            )
        # Remove script/style/noscript WITH their contents first: a bare
        # tag-strip leaves e.g. a styled-components CSS bundle as the
        # "description" of any SPA page (job #2646, the Ziflow case).
        text = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>", " ", r.text)
        # The pair-matching regex above needs a real closing tag; malformed
        # HTML with an unclosed <style>/<script>/<noscript> leaves it (and
        # everything after it) untouched — measured directly: CSS/JS text
        # then leaks into the description alongside real content. Every
        # WELL-FORMED pair is already gone at this point, so any tag of these
        # three names still present is unclosed by definition — truncate the
        # rest of the document there rather than trust an unbounded tail.
        text = re.split(r"(?is)<(?:script|style|noscript)\b", text, maxsplit=1)[0]
        text = re.sub(r"<[^>]+>", " ", text).strip()
        return re.sub(r"\s+", " ", text)[:8000], None
    except Exception as e:
        return None, (
            f"Error fetching URL: {e}\n"
            f"For pages that require login (LinkedIn, etc.), provide "
            f"'company', 'title', and 'description' manually."
        )
