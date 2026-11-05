"""Orchestrates tailored-CV generation for one job — cache, degrade, compile.

Opt-in by existence: no cv.pool in config (or the file missing) means the
feature is off and this function is a cheap None. Every failure path degrades
to None so the application always proceeds with the default CV.
"""

from enum import Enum, auto
from pathlib import Path
from typing import Any, Literal, NamedTuple

from moonlighter.application.cvgen.compile import looks_like_a_compiled_pdf
from moonlighter.application.cvgen.cv_template import (
    BaseFields,
    base_fields,
    relanguage_fallback_fields,
    template_text,
)
from moonlighter.application.cvgen.generate import USE_BASE, decide_cv
from moonlighter.application.cvgen.page_fit import TailoredCV, after_compile, fit_to_one_page
from moonlighter.application.cvgen.paths import generated_dir_for, resolved_pool_path
from moonlighter.application.cvgen.pool import CVPool, PoolError, load_pool
from moonlighter.application.cvgen.render import CVSelection
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger

logger = get_logger(__name__)


class _Cache(Enum):
    """The cache lookup's third answer: nothing is cached, go and generate.

    A cached PDF or a recompiled .tex is a TailoredCV, and the USE_BASE marker
    is a final None, so a bare None cannot also mean "nothing cached".
    """

    MISS = auto()


class _Generation(NamedTuple):
    config: dict[str, Any]
    pool: CVPool
    english_template: str
    base: BaseFields


def _output_directory(job: dict[str, Any], config: dict[str, Any]) -> Path | None:
    raw_id = job.get("id")
    if raw_id is None:
        # "never raises" is only total if an id-less job dict degrades too:
        # the cache is keyed on the job id, so there is nothing to generate.
        logger.warning("job has no id — using default CV")
        return None
    return generated_dir_for(config, int(raw_id))


def _cached_answer(out: Path) -> TailoredCV | _Cache | None:
    # Nothing here is revalidated, and nothing needs to be: a cached cv.tex can
    # only contain escaped model text (render._bullet_text), so recompiling one
    # cannot produce anything its generation did not already produce.
    # exists() alone is not enough (round-6 finding): a KeyboardInterrupt or an
    # external SIGKILL of moonlighter itself, between pdflatex's exit and this
    # check, can strand a truncated cv.pdf that would then be served forever —
    # looks_like_a_compiled_pdf sniffs for %%EOF and also rejects a directory.
    if looks_like_a_compiled_pdf(out / "cv.pdf"):
        return TailoredCV(out / "cv.pdf", compiled=True)
    if (out / "USE_BASE").exists():
        return None
    if (out / "cv.tex").exists():
        return after_compile(out / "cv.tex")  # a machine that gained latex since
    return _Cache.MISS


def _generation_inputs(pool_path: Path, config: dict[str, Any]) -> _Generation | None:
    try:
        pool = load_pool(pool_path)
    except PoolError as error:
        logger.warning("cv pool unusable, using default CV — %s", error)
        return None
    english_template = template_text(config, "en")
    if english_template is None:
        logger.warning("cv.template_dir has no cv-template.en.tex — using default CV")
        return None
    return _Generation(config, pool, english_template, base_fields(english_template))


async def _decision(
    job: dict[str, Any], profile: dict[str, Any], generation: _Generation, *, caller: LLMCaller
) -> CVSelection | Literal["use_base"] | None:
    try:
        return await decide_cv(job, generation.pool, profile, base=generation.base, caller=caller)
    except Exception as error:
        if is_spend_limit(error):
            logger.warning("spend limit during cv generation — using default CV")
            return None
        raise


def _materialised(
    selection: CVSelection | Literal["use_base"], generation: _Generation, out: Path
) -> TailoredCV | None:
    out.mkdir(parents=True, exist_ok=True)
    if selection == USE_BASE:
        (out / "USE_BASE").write_text("decided by the generation call\n")
        return None

    template = template_text(generation.config, selection.language) or generation.english_template
    final_selection = relanguage_fallback_fields(selection, template, generation.base)
    if final_selection is None:
        return None
    return fit_to_one_page(out, template, final_selection, pool=generation.pool)


async def ensure_tailored_cv(
    job: dict[str, Any],
    config: dict[str, Any],
    profile: dict[str, Any],
    *,
    caller: LLMCaller,
) -> TailoredCV | None:
    pool_path = resolved_pool_path(config)
    if not pool_path.exists():
        return None
    out = _output_directory(job, config)
    if out is None:
        return None
    cached = _cached_answer(out)
    if cached is not _Cache.MISS:
        return cached
    generation = _generation_inputs(pool_path, config)
    if generation is None:
        return None
    selection = await _decision(job, profile, generation, caller=caller)
    if selection is None:
        return None  # degraded generation — nothing written, next prepare retries
    return _materialised(selection, generation, out)
