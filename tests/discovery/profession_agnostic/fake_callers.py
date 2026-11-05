"""A nurse profile and a fake LLM caller that records the prompt it is given."""

NURSE_PROFILE = {
    "headline": "Registered Nurse",
    "summary": "Ten years of bedside nursing in intensive care.",
    "skills": ["Patient assessment", "Ventilator management"],
    "criteria": {"hard_filters": ["night shifts only"]},
}

SINGLE_RESPONSE = '{"score": 7.0, "score_notes": "ok", "caveats": []}'
BATCH_RESPONSE = '[{"score": 7.0, "score_notes": "ok"}, {"score": 6.0, "score_notes": "ok"}]'


def spy(response):
    seen = {}

    async def caller(prompt, model, cache_prefix=None):
        seen["prompt"] = prompt
        seen["prefix"] = cache_prefix
        return response

    return caller, seen
