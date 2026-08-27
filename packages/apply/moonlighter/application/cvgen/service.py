"""Orchestrates tailored-CV generation for one job — cache, degrade, compile.

Opt-in by existence: no cv.pool in config (or the file missing) means the
feature is off and this function is a cheap None. Every failure path degrades
to None so the application always proceeds with the default CV."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moonlighter.application.cvgen.compile import compile_pdf
from moonlighter.application.cvgen.generate import USE_BASE, decide_cv
from moonlighter.application.cvgen.pool import PoolError, load_pool
from moonlighter.application.cvgen.render import render_cv
from moonlighter.core.config import resolve_under_home
from moonlighter.core.llm import LLMCaller, is_spend_limit
from moonlighter.core.log import get_logger

logger = get_logger(__name__)

_BASE_SUMMARY = re.compile(r"^%%BASE_SUMMARY: (.+)$", re.MULTILINE)
_BASE_EXPERTISE = re.compile(r"^%%BASE_EXPERTISE: (.+)$", re.MULTILINE)
_MARKER_LINES = re.compile(r"^%%BASE_(SUMMARY|EXPERTISE): .+\n", re.MULTILINE)


@dataclass(frozen=True)
class TailoredCV:
    path: Path
    compiled: bool


def generated_dir_for(config: dict[str, Any], job_id: int) -> Path:
    base = (config.get("cv") or {}).get("generated_dir")
    root = resolve_under_home(base) if base else resolve_under_home("cv-generated")
    return root / str(job_id)


def _template(config: dict[str, Any], language: str) -> str | None:
    tdir = (config.get("cv") or {}).get("template_dir")
    if not tdir:
        return None
    en = resolve_under_home(tdir) / "cv-template.en.tex"
    pt = resolve_under_home(tdir) / "cv-template.pt.tex"
    if language == "pt":
        if pt.exists():
            return pt.read_text()
        logger.warning("no PT template — rendering the tailored CV in English")
    return en.read_text() if en.exists() else None


async def ensure_tailored_cv(
    job: dict[str, Any],
    config: dict[str, Any],
    profile: dict[str, Any],
    caller: LLMCaller,
) -> TailoredCV | None:
    pool_path = (config.get("cv") or {}).get("pool")
    if not pool_path or not resolve_under_home(pool_path).exists():
        return None
    raw_id = job.get("id")
    if raw_id is None:
        # "never raises" is only total if an id-less job dict degrades too:
        # the cache is keyed on the job id, so there is nothing to generate.
        logger.warning("job has no id — using default CV")
        return None
    out = generated_dir_for(config, int(raw_id))
    # Nothing here is revalidated, and nothing needs to be: a cached cv.tex can
    # only contain escaped model text (render._bullet_text), so recompiling one
    # cannot produce anything its generation did not already produce.
    if (out / "cv.pdf").exists():
        return TailoredCV(out / "cv.pdf", True)
    if (out / "USE_BASE").exists():
        return None
    if (out / "cv.tex").exists():
        pdf = compile_pdf(out / "cv.tex")  # a machine that gained latex since
        return TailoredCV(pdf, True) if pdf else TailoredCV(out / "cv.tex", False)

    try:
        pool = load_pool(resolve_under_home(pool_path))
    except PoolError as e:
        logger.warning("cv pool unusable, using default CV — %s", e)
        return None
    en_template = _template(config, "en")
    if en_template is None:
        logger.warning("cv.template_dir has no cv-template.en.tex — using default CV")
        return None
    base_summary = m.group(1) if (m := _BASE_SUMMARY.search(en_template)) else ""
    base_expertise = m.group(1) if (m := _BASE_EXPERTISE.search(en_template)) else ""

    try:
        selection = await decide_cv(job, pool, profile, base_summary, base_expertise, caller)
    except Exception as e:
        if is_spend_limit(e):
            logger.warning("spend limit during cv generation — using default CV")
            return None
        raise
    if selection is None:
        return None  # degraded generation — nothing written, next prepare retries
    out.mkdir(parents=True, exist_ok=True)
    if selection == USE_BASE:
        (out / "USE_BASE").write_text("decided by the generation call\n")
        return None

    template = _template(config, selection.language) or en_template
    tex = _MARKER_LINES.sub("", render_cv(template, selection, pool))
    (out / "cv.tex").write_text(tex)
    pdf = compile_pdf(out / "cv.tex")
    return TailoredCV(pdf, True) if pdf else TailoredCV(out / "cv.tex", False)
