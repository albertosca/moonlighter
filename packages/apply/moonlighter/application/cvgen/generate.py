"""One-call CV tailoring decision: USE_BASE or a validated selection.

The prompt's static prefix (profile + pool + instructions) is cacheable
across jobs; the suffix is the posting, untrusted-wrapped. Deterministic
validation keeps the model inside the pool: an id it invents is dropped,
never rendered (specs/2026-08-25-tailored-cv-design.md).
"""

from typing import Any, Final, Literal

from moonlighter.application.answers.operator_guard import find_operator_marker
from moonlighter.application.cvgen.cv_template import BaseFields
from moonlighter.application.cvgen.latex_text import is_typesettable
from moonlighter.application.cvgen.pool import CVPool
from moonlighter.application.cvgen.render import MAXIMUM_BULLETS, MAXIMUM_OPEN_SOURCE, CVSelection
from moonlighter.application.cvgen.selection_prompt import prompt_prefix
from moonlighter.core.llm.caller import LLMCaller
from moonlighter.core.llm.spend_limit import is_spend_limit
from moonlighter.core.log import get_logger
from moonlighter.core.parsing import parse_llm_json, wrap_untrusted

logger = get_logger(__name__)

# Sentinel for a genuine {"decision": "USE_BASE"} answer, distinct from None
# (degradation — parse failure, unrecognized output, operator-directed prose).
# The orchestrator (service.py) only writes its permanent USE_BASE marker file
# for this sentinel; None must let the next prepare retry.
USE_BASE: Final = "use_base"


def _known_ids(value: Any, known: frozenset[str]) -> tuple[str, ...]:
    """Pool ids out of whatever the model actually emitted for an id list.

    The posting is untrusted and steers the model's output SHAPE, not only its
    words: it can answer with a bare int, a string, or an object where a list
    belongs. Iterating that blindly raises TypeError, which travels out of
    ensure_tailored_cv and replaces the operator's whole application sheet with
    an error line — a far worse failure than losing the tailored CV. A field of
    the wrong shape therefore degrades to empty, which the renderer already
    handles: an experience with no validated bullets falls back to its first one
    (render.py's _entry — the one-page budget's rule), not all of them.
    """
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item in known)


def _cap(ids: tuple[str, ...], prose_ids: frozenset[str]) -> tuple[str, ...]:
    """At most MAXIMUM_BULLETS experience bullets, in the model's order.

    Prose ids ride along uncounted (prose entries render regardless — the id
    only carries a translation).
    """
    kept: list[str] = []
    count = 0
    for bullet_id in ids:
        if bullet_id in prose_ids:
            kept.append(bullet_id)
        elif count < MAXIMUM_BULLETS:
            kept.append(bullet_id)
            count += 1
    return tuple(kept)


def _curated_or_base(field: str, text: str, base: str) -> str | None:
    """Model prose for a whole-CV field, or the template's base text when the model's is unusable.

    None when there is no base to fall back to.

    Unusable = addressed to the operator, blank (is_typesettable("") is True,
    so an empty or whitespace-only field would otherwise pass straight
    through and render an empty section), or carrying a glyph outside the
    Latin allow-list. All three replace the field WHOLE: stripping one emoji
    from a sentence is a rewrite of what the model said, and the candidate
    signs it.
    """
    if find_operator_marker(text) is not None:
        logger.warning("cv %s addressed the operator — using default CV", field)
        return None
    if text.strip() and is_typesettable(text):
        return text
    if base:
        logger.warning(
            "cv %s is blank or carries non-Latin glyphs — using the base %s", field, field
        )
        return base
    logger.warning(
        "cv %s is blank or carries non-Latin glyphs and there is no base text — using default CV",
        field,
    )
    return None


def _vetted_translation(bullet_id: str, text: str) -> str | None:
    """The translation, or None (with a warning) when it must not reach the CV.

    Translations are prose in the same dialect as the summary, so they answer
    to the same operator-note guard and Latin allow-list — per bullet, since
    one bad translation only degrades that bullet.
    """
    if find_operator_marker(text) is not None:
        logger.warning(
            "translation for %s addressed the operator — keeping the pool bullet", bullet_id
        )
        return None
    if not is_typesettable(text):
        logger.warning(
            "translation for %s carries non-Latin glyphs — keeping the pool bullet", bullet_id
        )
        return None
    return text


def _usable_translations(raw_translations: Any, known: frozenset[str]) -> dict[str, str]:
    if not isinstance(raw_translations, dict):  # any other shape degrades the field
        return {}
    vetted = {
        key: _vetted_translation(key, str(value))
        for key, value in raw_translations.items()
        if key in known
    }
    return {key: text for key, text in vetted.items() if text is not None}


async def _model_answer(job: dict[str, Any], prefix: str, caller: LLMCaller) -> Any:
    """The model's parsed JSON answer, or None when the call or the parse failed."""
    suffix = wrap_untrusted(
        "job_posting",
        f"Company: {job.get('company')}\nTitle: {job.get('title')}\n"
        f"Description:\n{job.get('description') or ''}",
        cap=8000,
    )
    try:
        return parse_llm_json(await caller(suffix, "claude-sonnet-4-6", cache_prefix=prefix))
    except Exception as error:
        if is_spend_limit(error):
            raise  # quota is the orchestrator's call, not a silent degrade
        logger.warning("cv generation failed, using default CV — %s", error)
        return None


def _selection_from(data: dict[str, Any], pool: CVPool, base: BaseFields) -> CVSelection | None:
    known = pool.bullet_ids()
    # Operator-note guard: reject if generated prose is addressing the operator.
    # An operator-directed summary or expertise degrades the whole CV.
    summary = _curated_or_base("summary", str(data.get("summary") or ""), base.summary)
    expertise = _curated_or_base(
        "technical_expertise", str(data.get("technical_expertise") or ""), base.expertise
    )
    if summary is None or expertise is None:
        return None
    return CVSelection(
        language="pt" if data.get("language") == "pt" else "en",
        summary=summary,
        technical_expertise=expertise,
        bullets=_cap(_known_ids(data.get("bullets"), known), pool.prose_ids()),
        open_source=_known_ids(data.get("open_source"), known)[:MAXIMUM_OPEN_SOURCE],
        translations=_usable_translations(data.get("bullets_translated"), known),
    )


async def decide_cv(
    job: dict[str, Any],
    pool: CVPool,
    profile: dict[str, Any],
    *,
    base: BaseFields,
    caller: LLMCaller,
) -> CVSelection | Literal["use_base"] | None:
    data = await _model_answer(job, prompt_prefix(pool, profile, base), caller)
    if not isinstance(data, dict):
        return None  # unparseable shape — degrade, don't lock in
    decision = data.get("decision")
    if decision == "USE_BASE":
        return USE_BASE  # a genuine model answer, not a degradation
    if decision != "GENERATE":
        return None  # unrecognized decision — degrade, don't lock in
    return _selection_from(data, pool, base)
