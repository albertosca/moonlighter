"""Shared inputs for the tests that draft a pool from a profile."""

import json

CANDIDATE_PROFILE = {
    "name": "Jane Doe",
    "location": "Remote (Brazil)",
    "summary": "Senior engineer.",
    "skills": ["Python", "Go"],
    "experience": [
        {
            "company": "Acme Corp",
            "role": "Senior Software Engineer",
            "period": "2020 - present",
            "highlights": ["Led the migration of a monolith to services, cutting p99 by 40%."],
        }
    ],
}


DRAFT_RESPONSE = json.dumps(
    {
        "experiences": [
            {
                "company": "Acme Corp",
                "title": "Senior Software Engineer",
                "period": "2020 - present",
                "bullets": [
                    {
                        "id": "acme-migration",
                        "angles": ["backend"],
                        "text": "Led the migration of a monolith to services, cutting **p99 latency by 40%**.",
                    }
                ],
            }
        ],
        "open_source": [],
        "summary_facts": ["10+ years of experience"],
    }
)


def scripted_caller(response: str = DRAFT_RESPONSE):
    async def _call(prompt: str, model: str, cache_prefix: str | None = None) -> str:
        return response

    return _call
