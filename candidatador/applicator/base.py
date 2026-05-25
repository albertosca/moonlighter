import json
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from candidatador.parsing import _extract_json
from candidatador.llm import LLMCaller, _make_api_caller

async def _query_labels_with_fallback(page, selectors: list[str]) -> list:
    """
    Tenta cada seletor CSS em ordem até encontrar um que retorne elementos.
    Retorna a primeira lista não-vazia, ou [] se todos forem vazios.
    """
    for selector in selectors:
        results = await page.query_selector_all(selector)
        if results:
            return results
    return []

ANSWER_PROMPT = """You are filling out a job application on behalf of a senior software engineer.

## Candidate Profile
{profile_yaml}

## Job
Company: {company}
Title: {title}
Description: {description}

## Form Fields to Answer
{fields_list}

## Instructions
Return a JSON object mapping each field label (exactly as given) to the candidate's answer.
- Answers must be truthful based on the profile. Do not invent experience not listed.
- Answers should be specific, concise, and professional.
- For "Why [company]?" questions: focus on genuine technical interest.
- Keep answers under 300 words each.

Return only valid JSON (no markdown)."""

@dataclass
class ApplicationDraft:
    job_id: int
    answers: dict[str, str]
    form_fields: list[str]
    error: Optional[str] = None

class BaseApplier(ABC):
    def __init__(self, page, config: dict, profile: dict):
        self.page = page
        self.config = config
        self.profile = profile

    @abstractmethod
    async def detect(self) -> bool:
        """Return True if current page is this ATS."""
        ...

    @abstractmethod
    async def extract_fields(self) -> list[str]:
        """Extract all form field labels from the application form."""
        ...

    @abstractmethod
    async def fill_form(self, answers: dict[str, str], cv_path: str) -> None:
        """Fill the form with the given answers and upload CV."""
        ...

    @abstractmethod
    async def submit(self) -> bool:
        """Submit the form. Return True on success."""
        ...

async def generate_answers(
    company: str,
    title: str,
    description: str,
    fields: list[str],
    profile: dict,
    model: str = "claude-sonnet-4-6",
    job_id: int = 0,
    _caller: LLMCaller | None = None,
) -> ApplicationDraft:
    if _caller is None:
        _caller = _make_api_caller(max_tokens=2048)
    prompt = ANSWER_PROMPT.format(
        profile_yaml=yaml.dump(profile, allow_unicode=True),
        company=company,
        title=title,
        description=description[:4000],
        fields_list="\n".join(f"- {f}" for f in fields),
    )
    try:
        raw_text = await _caller(prompt, model)
        raw = _extract_json(raw_text)
        answers = json.loads(raw)
        return ApplicationDraft(job_id=job_id, answers=answers, form_fields=fields)
    except Exception as e:
        return ApplicationDraft(job_id=job_id, answers={}, form_fields=fields, error=str(e))
