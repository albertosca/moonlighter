"""Classifying a reply through the LLM: each type, the model passed, and malformed answers."""

import json

import pytest
from moonlighter.tracking.classification import ClassificationError, classify_response

from tests.tracking.llm_callers import make_llm_caller
from tests.tracking.tracking_settings import BASE_EMAIL, BASE_STAGES


@pytest.fixture
def message():
    return {
        "to": BASE_EMAIL,
        "from_": "recruiter@anthropic.com",
        "subject": "Next steps",
        "body": "We would like to schedule a technical interview.",
    }


class TestClassifyResponse:
    async def test_returns_interview_type(self, message):
        caller = make_llm_caller(
            {
                "type": "interview",
                "stage": "technical_interview",
                "new_stage": None,
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "Technical interview scheduled.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "interview"
        assert result["stage"] == "technical_interview"
        assert result["company"] == "Anthropic"

    async def test_passes_model_to_caller(self, message):
        """Regression BUG-02: the real caller (call_cli, or make_api_caller's) requires (prompt, model)
        with no default. classify_response must pass the model positionally.
        """
        received = {}

        async def strict_caller(prompt, model):  # no default → catches a 1-arg call
            received["model"] = model
            return json.dumps({"type": "unrelated", "summary": ""})

        await classify_response(message, BASE_STAGES, strict_caller, model="claude-test")
        assert received["model"] == "claude-test"

    async def test_returns_rejection(self, message):
        caller = make_llm_caller(
            {
                "type": "rejection",
                "stage": None,
                "new_stage": None,
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "Unfortunately we won't be moving forward.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "rejection"
        assert result["stage"] is None

    async def test_returns_offer(self, message):
        caller = make_llm_caller(
            {
                "type": "offer",
                "stage": None,
                "new_stage": None,
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "Formal offer sent.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "offer"

    async def test_returns_screening(self, message):
        caller = make_llm_caller(
            {
                "type": "screening",
                "stage": "phone_screening",
                "new_stage": None,
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "Initial 30min call.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "screening"
        assert result["stage"] == "phone_screening"

    async def test_returns_info_request(self, message):
        caller = make_llm_caller(
            {
                "type": "info_request",
                "stage": None,
                "new_stage": None,
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "We need more information.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "info_request"

    async def test_returns_unrelated(self, message):
        caller = make_llm_caller(
            {
                "type": "unrelated",
                "stage": None,
                "new_stage": None,
                "company": None,
                "job_title": None,
                "summary": "Newsletter de marketing.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["type"] == "unrelated"

    async def test_new_stage_populated_when_llm_proposes_unknown(self, message):
        caller = make_llm_caller(
            {
                "type": "interview",
                "stage": "pair_programming",
                "new_stage": "pair_programming",
                "company": "Anthropic",
                "job_title": "Senior Engineer",
                "summary": "Pair programming session.",
            }
        )
        result = await classify_response(message, BASE_STAGES, caller)
        assert result["new_stage"] == "pair_programming"

    async def test_json_fence_in_llm_response_handled(self, message):
        raw = {
            "type": "rejection",
            "stage": None,
            "new_stage": None,
            "company": "X",
            "job_title": "Eng",
            "summary": "Rejected.",
        }

        async def caller_with_fence(prompt, model=None):
            return f"```json\n{json.dumps(raw)}\n```"

        result = await classify_response(message, BASE_STAGES, caller_with_fence)
        assert result["type"] == "rejection"

    async def test_malformed_llm_response_raises_classification_error(self, message):
        """A response that can't be parsed is a FAILED classification, not a
        successful classification of 'unrelated' — see ClassificationError's
        docstring (whole-branch Finding 1): treating parse failure as
        'unrelated' let sync_responses mark the message permanently processed,
        losing a real reply the model simply failed to answer for.
        """

        async def bad_caller(prompt, model=None):
            return "not JSON"

        with pytest.raises(ClassificationError):
            await classify_response(message, BASE_STAGES, bad_caller)
