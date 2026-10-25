"""The candidate's identity comes from the profile, never from the code (#120).

Idea credit: JR2PROJETOS (`profession-agnostic` branch on their fork); the code is ours.
Every test here inspects the text actually sent to a fake LLM caller, or the URL/keyword
a scanner is actually given.
"""

from unittest.mock import AsyncMock, patch

import pytest
from moonlighter.core.config import ConfigError, validate_config
from moonlighter.discovery import service as scan_service
from moonlighter.discovery.evaluator import (
    EvalInput,
    engagement_section,
    evaluate_job,
    evaluate_jobs_batch,
)
from moonlighter.discovery.sources.http import RemotiveScanner, WeWorkRemotelyScanner

NURSE_PROFILE = {
    "headline": "Registered Nurse",
    "summary": "Ten years of bedside nursing in intensive care.",
    "skills": ["Patient assessment", "Ventilator management"],
    "criteria": {"hard_filters": ["night shifts only"]},
}

# Words that would betray a hardcoded software-engineer, Brazilian, permanent-role candidate.
FORBIDDEN = (
    "software",
    "engineer",
    "brazil",
    "latam",
    "permanent full-time",
    "technical expertise",
)

SINGLE_RESPONSE = '{"score": 7.0, "score_notes": "ok", "caveats": []}'
BATCH_RESPONSE = '[{"score": 7.0, "score_notes": "ok"}, {"score": 6.0, "score_notes": "ok"}]'


def _spy(response):
    seen = {}

    async def caller(prompt, model, cache_prefix=None):
        seen["prompt"] = prompt
        seen["prefix"] = cache_prefix
        return response

    return caller, seen


def _assert_no_hardcoded_identity(text):
    lowered = text.lower()
    for word in FORBIDDEN:
        assert word not in lowered, f"{word!r} leaked into a prompt for a nurse profile"


async def test_single_evaluation_prompt_has_no_software_identity():
    caller, seen = _spy(SINGLE_RESPONSE)
    await evaluate_job(
        "Hospital", "ICU Nurse", "Care for patients.", NURSE_PROFILE, "m", caller,
        location="Lisbon", remote_type="onsite",
    )  # fmt: skip
    _assert_no_hardcoded_identity(seen["prefix"])
    assert "Registered Nurse" in seen["prefix"]
    assert "described below" in seen["prefix"]
    assert "## Engagement type" not in seen["prefix"]


async def test_batch_evaluation_prompt_has_no_software_identity():
    caller, seen = _spy(BATCH_RESPONSE)
    jobs = [EvalInput("Hospital", "ICU Nurse", "Care."), EvalInput("Clinic", "Nurse", "Care.")]
    await evaluate_jobs_batch(jobs, NURSE_PROFILE, "m", caller)
    _assert_no_hardcoded_identity(seen["prefix"])
    assert "## Engagement type" not in seen["prefix"]


async def test_the_engagement_the_profile_names_reaches_both_prompts():
    profile = {**NURSE_PROFILE, "preferences": {"engagement": "part-time hospital"}}
    caller, seen = _spy(SINGLE_RESPONSE)
    await evaluate_job(
        "Hospital", "Nurse", "Care.", profile, "m", caller, location=None, remote_type=None
    )
    assert "targets part-time hospital positions" in seen["prefix"]
    caller, seen = _spy(BATCH_RESPONSE)
    await evaluate_jobs_batch(
        [EvalInput("A", "B", "C"), EvalInput("D", "E", "F")], profile, "m", caller
    )
    assert "targets part-time hospital positions" in seen["prefix"]


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"preferences": None},
        {"preferences": {}},
        {"preferences": {"engagement": ""}},
        {"preferences": {"engagement": "   "}},
        {"preferences": {"engagement": 3}},
    ],
)
def test_engagement_unknown_means_no_section(profile):
    assert engagement_section(profile) == ""


def test_engagement_text_is_inserted_verbatim_even_with_braces():
    section = engagement_section({"preferences": {"engagement": "{weird} full-time"}})
    assert "targets {weird} full-time positions" in section


async def test_remotive_asks_for_no_category_unless_configured():
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exit_arguments):
            return False

    urls = []

    async def fake_get_json(client, url):
        urls.append(url)
        return {"jobs": []}

    with (
        patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=Client()),
        patch("moonlighter.discovery.sources.http.get_json", fake_get_json),
    ):
        await RemotiveScanner().scan()
        await RemotiveScanner().scan(category="customer-support")
        await RemotiveScanner().scan(category="data & ai")
    assert urls == [
        "https://remotive.com/api/remote-jobs",
        "https://remotive.com/api/remote-jobs?category=customer-support",
        "https://remotive.com/api/remote-jobs?category=data%20%26%20ai",
    ]
    assert "software-dev" not in RemotiveScanner.BASE


async def test_remotive_dispatch_passes_the_configured_category():
    with patch("moonlighter.discovery.sources.http.RemotiveScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        await scan_service._scan_remotive(
            {"scan_remotive": True, "remotive_category": "design"}, {}, ""
        )
    MockScanner.return_value.scan.assert_awaited_once_with(category="design", stats={})


async def _collect(keywords, config):
    with (
        patch("moonlighter.discovery.service.build_http_scanners", return_value={}),
        patch("moonlighter.discovery.service.discover_entry_points", return_value=[]),
    ):
        return await scan_service._collect_raw_jobs(keywords, config, {})


@pytest.mark.parametrize("keywords", ["", "   "])
async def test_gupy_without_keywords_is_skipped_with_a_warning_not_searched_as_software(keywords):
    with patch("moonlighter.discovery.sources.http.GupyScanner") as MockGupy:
        MockGupy.return_value.scan = AsyncMock(return_value=[])
        raw_jobs, warning = await _collect(keywords, {"scan_gupy": True})
    MockGupy.return_value.scan.assert_not_called()
    assert raw_jobs == []
    assert warning is not None
    assert "scan_gupy" in warning
    assert "software" not in warning.lower()


async def test_gupy_off_and_no_keywords_says_nothing():
    _, warning = await _collect("", {})
    assert warning is None


async def test_gupy_with_keywords_searches_exactly_them():
    with patch("moonlighter.discovery.sources.http.GupyScanner") as MockGupy:
        MockGupy.return_value.scan = AsyncMock(return_value=[])
        await _collect("enfermeiro", {"scan_gupy": True})
    assert MockGupy.return_value.scan.await_args.kwargs["keywords"] == "enfermeiro"


async def test_wwr_reads_the_all_jobs_feed_unless_a_category_is_configured():
    from unittest.mock import MagicMock

    fetched = []

    async def fake_get(url, **_keyword_arguments):
        fetched.append(url)
        response = MagicMock()
        response.status_code = 200
        response.text = "<rss><channel></channel></rss>"
        return response

    client = MagicMock()
    client.get = fake_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("moonlighter.discovery.sources.http.httpx.AsyncClient", return_value=client):
        await WeWorkRemotelyScanner().scan()
        await WeWorkRemotelyScanner().scan(category="design")
        await WeWorkRemotelyScanner().scan(category="../x")
    assert fetched == [
        "https://weworkremotely.com/remote-jobs.rss",
        "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "https://weworkremotely.com/categories/remote-..%2Fx-jobs.rss",
    ]
    assert "programming" not in WeWorkRemotelyScanner.BASE


async def test_wwr_dispatch_passes_the_configured_category():
    with patch("moonlighter.discovery.sources.http.WeWorkRemotelyScanner") as MockScanner:
        MockScanner.return_value.scan = AsyncMock(return_value=[])
        await scan_service._scan_wwr({"scan_wwr": True, "wwr_category": "design"}, {}, "")
    MockScanner.return_value.scan.assert_awaited_once_with(category="design", stats={})


@pytest.mark.parametrize("key", ["remotive_category", "wwr_category"])
def test_category_config_keys_are_strings(key):
    validate_config({key: "design"})
    with pytest.raises(ConfigError, match=key):
        validate_config({key: 3})
