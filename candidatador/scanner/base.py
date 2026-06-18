from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class RawJob:
    source: str
    company: str
    title: str
    url: str
    location: str | None = None
    remote_type: str | None = None  # 'remote' | 'hybrid' | 'onsite'
    description: str | None = None
    posted_at: datetime | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_source: str | None = None  # 'stated' only (scanner doesn't infer)


def normalize_remote_type(location: str | None) -> str | None:
    if not location:
        return None
    loc = location.lower()
    if "hybrid" in loc:
        return "hybrid"
    if "remote" in loc:
        return "remote"
    return "onsite"


class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, company_slugs: list[str], **kwargs: Any) -> list[RawJob]:
        """Fetch raw job listings. Returns deduplicated list of RawJob."""
        ...
