"""Loads and validates the curated CV bullet pool (profile/cv-pool.yaml).

The pool is the factual boundary of CV generation: the LLM selects ids from
it, never authors content (specs/2026-08-25-tailored-cv-design.md)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PoolError(Exception):
    """The pool file is missing or malformed — named precisely so the operator
    can fix the YAML instead of silently losing the tailored-CV feature."""


@dataclass(frozen=True)
class PoolBullet:
    id: str
    angles: tuple[str, ...]
    latex: str


@dataclass(frozen=True)
class PoolExperience:
    company: str
    title: str
    period: str
    location: str
    bullets: tuple[PoolBullet, ...]
    prose: str | None
    prose_id: str | None
    angles: tuple[str, ...]


@dataclass(frozen=True)
class CVPool:
    experiences: tuple[PoolExperience, ...]
    open_source: tuple[PoolBullet, ...]
    summary_facts: tuple[str, ...]

    def bullet_ids(self) -> frozenset[str]:
        return frozenset(_all_ids(self))


def _all_ids(pool: CVPool) -> list[str]:
    """Every id the pool defines, in order and with duplicates kept.

    One definition for both callers: bullet_ids() (the generator's allow-list)
    and load_pool's duplicate check. Two copies drift the moment a new kind of
    id is added to one of them.
    """
    ids = [b.id for e in pool.experiences for b in e.bullets]
    ids += [e.prose_id for e in pool.experiences if e.prose_id]
    ids += [b.id for b in pool.open_source]
    return ids


def _bullet(raw: Any) -> PoolBullet:
    if not isinstance(raw, dict):
        # Hand-curated YAML: a stray '-' makes an entry a bare string, and
        # raw.get() would raise AttributeError right past the caller's
        # `except PoolError` — taking the whole tool call down with it.
        raise PoolError(f"bullet is not a mapping: {raw!r}")
    for field in ("id", "latex"):
        if not raw.get(field):
            raise PoolError(f"bullet missing '{field}': {raw!r}")
    return PoolBullet(
        id=str(raw["id"]),
        angles=tuple(str(a) for a in raw.get("angles") or ()),
        latex=str(raw["latex"]),
    )


def _experience(raw: Any) -> PoolExperience:
    if not isinstance(raw, dict):
        raise PoolError(f"experience is not a mapping: {raw!r}")
    for field in ("company", "title", "period", "location"):
        if not raw.get(field):
            raise PoolError(f"experience missing '{field}': {raw!r}")
    bullets = tuple(_bullet(b) for b in raw.get("bullets") or ())
    prose = raw.get("prose")
    if not bullets and not prose:
        raise PoolError(f"experience '{raw['company']}' has neither bullets or prose")
    return PoolExperience(
        company=str(raw["company"]),
        title=str(raw["title"]),
        period=str(raw["period"]),
        location=str(raw["location"]),
        bullets=bullets,
        prose=str(prose) if prose else None,
        prose_id=str(raw["id"]) if raw.get("id") else None,
        angles=tuple(str(a) for a in raw.get("angles") or ()),
    )


def load_pool(path: Path) -> CVPool:
    if not path.exists():
        raise PoolError(f"pool file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise PoolError(f"pool file failed to parse: {e}") from e
    if not isinstance(raw, dict) or not raw.get("experiences"):
        raise PoolError("pool file has no 'experiences' list")
    pool = CVPool(
        experiences=tuple(_experience(e) for e in raw["experiences"]),
        open_source=tuple(_bullet(b) for b in raw.get("open_source") or ()),
        summary_facts=tuple(str(f) for f in raw.get("summary_facts") or ()),
    )
    ids = _all_ids(pool)
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise PoolError(f"duplicate bullet ids: {dupes}")
    return pool
