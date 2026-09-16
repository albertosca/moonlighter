"""Job-URL normalization for dedup.

Recruitee's API returns apply URLs ending in /c/new while a human pastes the
posting URL without it; dedup is exact-string on URL, so the same posting could
occupy two rows. Normalizing both sides of every comparison closes that.
Historical rows keep their stored form — the seen-set is normalized at read
time, new rows are stored normalized.
"""


def normalize_job_url(url: str) -> str:
    """Normalize a job posting URL by removing apply-suffix and trailing slashes.

    Recruitee's API returns apply URLs ending in /c/new which may not match
    the human-pasted posting URL, causing false positives in dedup checks.
    This function strips the suffix and normalizes whitespace.
    """
    url = url.strip().rstrip("/")
    if url.endswith("/c/new"):
        url = url.removesuffix("/c/new")
    return url
