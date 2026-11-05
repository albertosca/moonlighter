"""Asks the model which job-title patterns are safe to block, and reads its answer.

A pattern is proposed per company from the titles a real evaluation scored low. The answer
comes back as a JSON array; only entries the model marked safe survive.
"""

import json
from typing import Any

from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.parsing import extract_json

TITLE_CAP = 80  # titles sent per company: more only inflates the context
QUOTA_MARKERS = (
    "spend limit",
    "quota",
    "rate limit",
    "too many requests",
    "overloaded",
    "429",
    "usage limit",
)


def is_quota_error(error: Exception) -> bool:
    """Whether the error says the account ran out of quota, so asking again is pointless."""
    error_text = str(error).lower()
    return any(marker in error_text for marker in QUOTA_MARKERS)


def proposal_prompt(
    company: str, titles: list[str], threshold: float, *, profile: dict[str, Any]
) -> str:
    """The prompt asking the model for safe title patterns, from the company's low-scored titles."""
    titles_block = "\n".join(f"- {title}" for title in titles[:TITLE_CAP])
    name = profile.get("name", "the candidate")
    level = profile.get("level", "senior software engineer")
    skills = ", ".join((profile.get("top_skills") or [])[:4]) or "software engineering"
    return f"""\
You are building a job title blocklist for {name}, a {level} specializing in {skills}.

The following job titles at **{company}** were evaluated and scored {threshold} or below out of 10 \
— meaning they are clearly irrelevant for them:

{titles_block}

Your task: propose minimal, safe **substring patterns** (lowercase) to block future titles like these \
before they reach the LLM evaluator.

A pattern is SAFE only if you are confident that **every possible job title containing it** would be \
irrelevant for a senior software engineer. When in doubt, mark safe=false.

Examples of UNSAFE patterns (too broad):
- "analista" alone → "analista de segurança" could be relevant
- "gerente" alone → "Engineering Manager" might appear in PT-BR as "Gerente de Engenharia"
- "especialista" alone → "Especialista de Plataforma" could be a tech role

Examples of SAFE patterns:
- "gerente de relacionamento" → always a banking relationship manager, never engineering
- "banco de talentos" → always a talent pool post, not a real opening
- "estagiár" → always an intern position

Return a JSON array (no markdown):
[
  {{
    "pattern": "lowercase substring to match",
    "examples": ["example title 1", "example title 2"],
    "safe": true,
    "reasoning": "one sentence explaining why all matching titles would be irrelevant"
  }}
]

Return [] if no safe patterns can be identified.\
"""


async def propose_for_company(
    company: str, prompt: str, *, caller: LLMCaller, model: str
) -> list[dict[str, Any]]:
    """The safe proposals the model returns for one company; a quota error is re-raised."""
    try:
        raw = await caller(prompt, model)
        proposals = json.loads(extract_json(raw))
        if not isinstance(proposals, list):
            return []
        return [
            proposal
            for proposal in proposals
            if isinstance(proposal, dict)
            and proposal.get("safe") is True
            and proposal.get("pattern")
        ]
    except Exception as error:
        if is_quota_error(error):
            raise
        print(f"  ⚠️  Error processing {company}: {error}")
        return []
