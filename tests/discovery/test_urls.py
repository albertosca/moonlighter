"""Tests for job URL normalization."""

from moonlighter.discovery.urls import normalize_job_url


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
