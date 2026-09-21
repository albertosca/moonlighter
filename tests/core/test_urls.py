"""Tests for job URL normalization."""

from moonlighter.core.urls import normalize_job_url


def test_strips_recruitee_apply_suffix():
    assert (
        normalize_job_url("https://jobs.channable.com/o/backend-engineer/c/new")
        == "https://jobs.channable.com/o/backend-engineer"
    )


def test_strips_trailing_slash_then_suffix():
    assert (
        normalize_job_url("https://x.recruitee.com/o/dev/c/new/") == "https://x.recruitee.com/o/dev"
    )


def test_leaves_ordinary_urls_alone():
    url = "https://boards.greenhouse.io/stripe/jobs/123"
    assert normalize_job_url(url) == url


def test_strips_utm_params():
    assert (
        normalize_job_url(
            "https://boards.greenhouse.io/stripe/jobs/123?utm_source=li&utm_campaign=foo"
        )
        == "https://boards.greenhouse.io/stripe/jobs/123"
    )


def test_strips_ref_and_source_params():
    assert (
        normalize_job_url("https://boards.greenhouse.io/stripe/jobs/123?ref=twitter&source=indeed")
        == "https://boards.greenhouse.io/stripe/jobs/123"
    )


def test_keeps_non_tracking_params():
    assert (
        normalize_job_url("https://boards.greenhouse.io/stripe/jobs/123?gh_jid=123&utm_source=li")
        == "https://boards.greenhouse.io/stripe/jobs/123?gh_jid=123"
    )


def test_manually_pasted_url_with_utm_dedups_against_clean_scanned_url():
    pasted = "https://boards.greenhouse.io/stripe/jobs/123?utm_source=linkedin"
    scanned = "https://boards.greenhouse.io/stripe/jobs/123"
    assert normalize_job_url(pasted) == normalize_job_url(scanned)


def test_strips_tracking_params_before_recruitee_suffix():
    assert (
        normalize_job_url("https://x.recruitee.com/o/dev/c/new?utm_source=li")
        == "https://x.recruitee.com/o/dev"
    )
