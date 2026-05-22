from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class RawJob:
    source: str
    company: str
    title: str
    url: str
    location: Optional[str] = None
    remote_type: Optional[str] = None    # 'remote' | 'hybrid' | 'onsite'
    description: Optional[str] = None
    posted_at: Optional[datetime] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    salary_source: Optional[str] = None  # 'stated' only (scanner doesn't infer)

def normalize_remote_type(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    loc = location.lower()
    if "remote" in loc:
        return "remote"
    if "hybrid" in loc:
        return "hybrid"
    return "onsite"

class BaseScanner(ABC):
    @abstractmethod
    async def scan(self, company_slugs: list[str], **kwargs) -> list[RawJob]:
        """Fetch raw job listings. Returns deduplicated list of RawJob."""
        ...
