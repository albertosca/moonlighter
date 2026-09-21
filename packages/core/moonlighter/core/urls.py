"""Job-URL normalization for dedup.

Recruitee's API returns apply URLs ending in /c/new while a human pastes the
posting URL without it; dedup is exact-string on URL, so the same posting could
occupy two rows. Normalizing both sides of every comparison closes that.
Historical rows keep their stored form — the seen-set is normalized at read
time, new rows are stored normalized.

Tracking query parameters (utm_*, ref, source) are stripped for the same
reason: a manually pasted URL with a campaign tag and the same posting found
later by a scan (clean URL) would otherwise occupy two rows. Only that known
set is stripped — no scanner in this codebase puts a job's identity in `ref`
or `source`, but an ATS whose job id lives in the query string (e.g. a
`gh_jid`-style param) must keep it, so nothing else is touched.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {"ref", "source"}


def _strip_tracking_params(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def normalize_job_url(url: str) -> str:
    """Normalize a job posting URL for dedup: strip tracking params, the
    Recruitee apply-suffix, and trailing slashes/whitespace.

    Recruitee's API returns apply URLs ending in /c/new which may not match
    the human-pasted posting URL, causing false positives in dedup checks.
    This function strips the suffix, known tracking query params, and
    normalizes whitespace.
    """
    url = _strip_tracking_params(url.strip()).rstrip("/")
    if url.endswith("/c/new"):
        url = url.removesuffix("/c/new")
    return url
