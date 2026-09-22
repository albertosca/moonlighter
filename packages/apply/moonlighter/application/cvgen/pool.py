"""Loads and validates the curated CV bullet pool (profile/cv-pool.yaml).

The pool is the factual boundary of CV generation: the LLM selects ids from
it, never authors content (specs/2026-08-25-tailored-cv-design.md)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PoolError(Exception):
    """The pool file is missing or malformed — named precisely so the operator
    can fix the YAML instead of silently losing the tailored-CV feature."""


# A fixed field is pasted into \cventry{} as-is (it is operator LaTeX, like the
# bullets), so a bare special breaks EVERY compile. The draft's "R&D Engineer"
# did exactly that, silently, until someone compiled it.
# A single backslash escapes the special; an even number of backslashes leaves
# it unescaped (e.g., \\& is line-break + unescaped ampersand, which breaks).
_SPECIAL_WITH_BACKSLASHES = re.compile(r"(\\*)([&%$#_])")


def _fixed_field(raw: dict[str, Any], field: str) -> str:
    value = str(raw[field])
    for m in _SPECIAL_WITH_BACKSLASHES.finditer(value):
        backslashes = m.group(1)
        special = m.group(2)
        # Even number of backslashes (including 0) means the special is unescaped
        if len(backslashes) % 2 == 0:
            raise PoolError(f"unescaped '{special}' in '{field}': {value!r} (write \\{special})")
    return value


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

    def prose_ids(self) -> frozenset[str]:
        return frozenset(e.prose_id for e in self.experiences if e.prose_id)


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
    if bullets and prose:
        raise PoolError(f"experience '{raw['company']}' has both prose and bullets")
    return PoolExperience(
        company=_fixed_field(raw, "company"),
        title=_fixed_field(raw, "title"),
        period=_fixed_field(raw, "period"),
        location=_fixed_field(raw, "location"),
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


def _bullet_dict(bullet: PoolBullet) -> dict[str, Any]:
    return {"id": bullet.id, "angles": list(bullet.angles), "latex": bullet.latex}


def _experience_dict(exp: PoolExperience) -> dict[str, Any]:
    out: dict[str, Any] = {
        "company": exp.company,
        "title": exp.title,
        "period": exp.period,
        "location": exp.location,
    }
    if exp.angles:
        out["angles"] = list(exp.angles)
    if exp.prose is not None:
        out["id"] = exp.prose_id
        out["prose"] = exp.prose
    else:
        out["bullets"] = [_bullet_dict(b) for b in exp.bullets]
    return out


def dump_pool(pool: CVPool) -> str:
    """The inverse of load_pool: a CVPool serialized back to the exact YAML
    shape load_pool parses (round-trips). Used by the bootstrap (Task 6) to
    write a freshly drafted pool -- never by anything that reads a
    hand-curated one, so there is no risk of silently reformatting an
    operator's own file."""
    raw: dict[str, Any] = {"experiences": [_experience_dict(e) for e in pool.experiences]}
    if pool.open_source:
        raw["open_source"] = [_bullet_dict(b) for b in pool.open_source]
    if pool.summary_facts:
        raw["summary_facts"] = list(pool.summary_facts)
    result = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=100)
    return result if isinstance(result, str) else ""
