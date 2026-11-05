import json

import pytest
from moonlighter.application.cvgen.bootstrap_error import BootstrapError
from moonlighter.application.cvgen.pool_draft import draft_pool

from tests.application.cvgen.bootstrap_samples import CANDIDATE_PROFILE, scripted_caller


async def test_draft_pool_raises_when_the_profile_has_no_experience():
    with pytest.raises(BootstrapError, match="no experience"):
        await draft_pool({"name": "Jane"}, scripted_caller())


async def test_draft_pool_raises_when_the_model_response_is_unusable():
    with pytest.raises(BootstrapError, match="could not be parsed"):
        await draft_pool(CANDIDATE_PROFILE, scripted_caller("not json"))


async def test_draft_pool_reraises_a_spend_limit():
    async def _quota_exceeded(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("spend limit reached")

    with pytest.raises(RuntimeError, match="spend limit"):
        await draft_pool(CANDIDATE_PROFILE, _quota_exceeded)


async def test_draft_pool_skips_an_experience_entry_missing_a_company():
    no_company_response = json.dumps(
        {
            "experiences": [
                {
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "x", "angles": [], "text": "No company here"}],
                },
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                },
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(no_company_response))
    assert [error.company for error in pool.experiences] == ["Acme"]


async def test_draft_pool_drops_an_experience_when_every_bullet_is_dropped():
    dropped_response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Bad Co",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "bad", "angles": [], "text": "Shipped it 🚀"}],
                },
                {
                    "company": "Acme",
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "acme-ok", "angles": [], "text": "Shipped it well"}],
                },
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    pool = await draft_pool(CANDIDATE_PROFILE, scripted_caller(dropped_response))
    assert [error.company for error in pool.experiences] == ["Acme"]


async def test_draft_pool_raises_when_the_call_fails_for_a_non_spend_limit_reason():
    async def _broken(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        raise RuntimeError("connection reset")

    with pytest.raises(BootstrapError, match="drafting call failed"):
        await draft_pool(CANDIDATE_PROFILE, _broken)


async def test_draft_pool_raises_when_the_response_has_no_experiences_key():
    with pytest.raises(BootstrapError, match="could not be parsed into a CV pool"):
        await draft_pool(CANDIDATE_PROFILE, scripted_caller(json.dumps({"foo": "bar"})))


async def test_draft_pool_raises_when_every_experience_is_unusable():
    unusable_response = json.dumps(
        {
            "experiences": [
                {
                    "title": "Eng",
                    "period": "2020",
                    "bullets": [{"id": "x", "angles": [], "text": "No company"}],
                }
            ],
            "open_source": [],
            "summary_facts": [],
        }
    )
    with pytest.raises(BootstrapError, match="no usable experience"):
        await draft_pool(CANDIDATE_PROFILE, scripted_caller(unusable_response))
