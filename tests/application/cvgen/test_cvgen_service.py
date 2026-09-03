import json
from pathlib import Path
from unittest.mock import patch

import pytest
from moonlighter.application.cvgen.service import (
    TailoredCV,
    ensure_tailored_cv,
    generated_dir_for,
)

POOL_YAML = """
experiences:
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
"""
TEMPLATE = (
    "%%BASE_SUMMARY: The base summary line\n"
    "%%BASE_EXPERTISE: Elixir, React\n"
    "\\cvlistitem{%%SUMMARY%%}\n\\cvlistitem{%%TECHNICAL_EXPERTISE%%}\n"
    "%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"
)
JOB = {"id": 42, "title": "Eng", "company": "acme", "description": "d"}
GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a"],
        "open_source": [],
    }
)


@pytest.fixture
def cfg(tmp_path):
    pool = tmp_path / "cv-pool.yaml"
    pool.write_text(POOL_YAML)
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "cv-template.en.tex").write_text(TEMPLATE)
    return {
        "cv": {
            "pool": str(pool),
            "template_dir": str(tdir),
            "generated_dir": str(tmp_path / "generated"),
        }
    }


def _caller(response=GENERATE):
    calls = {"n": 0}

    async def call(prompt, model, cache_prefix=None):
        calls["n"] += 1
        return response

    return call, calls


async def test_no_pool_configured_is_none_without_calls(tmp_path):
    call, calls = _caller()
    assert await ensure_tailored_cv(JOB, {"cv": {}}, {}, call) is None
    assert calls["n"] == 0


async def test_generates_writes_tex_and_compiles(cfg):
    call, _ = _caller()
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    out = generated_dir_for(cfg, 42)
    assert (out / "cv.tex").exists()
    assert "Did A" in (out / "cv.tex").read_text()
    assert "The base summary line" not in (out / "cv.tex").read_text()  # markers stripped


async def test_use_base_writes_marker_and_skips_next_time(cfg):
    call, calls = _caller(json.dumps({"decision": "USE_BASE"}))
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert (generated_dir_for(cfg, 42) / "USE_BASE").exists()
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 1  # second call served by the marker


async def test_existing_pdf_short_circuits(cfg):
    out = generated_dir_for(cfg, 42)
    out.mkdir(parents=True)
    (out / "cv.pdf").write_bytes(b"%PDF")
    call, calls = _caller()
    result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result == TailoredCV(out / "cv.pdf", True)
    assert calls["n"] == 0  # the no-LLM-call-on-cache-hit contract


async def test_no_latex_returns_tex_uncompiled(cfg):
    call, _ = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=False),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result is not None and not result.compiled
    assert result.path.suffix == ".tex"


async def test_generation_failure_degrades_to_none(cfg):
    call, _ = _caller("garbage")
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    # A transient malformed response must NOT write the permanent USE_BASE
    # marker — that would disable tailored-CV generation for this job forever.
    assert not (generated_dir_for(cfg, 42) / "USE_BASE").exists()
    good_call, good_calls = _caller()
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        retry = await ensure_tailored_cv(JOB, cfg, {}, good_call)
    assert isinstance(retry, TailoredCV) and retry.compiled
    assert good_calls["n"] == 1  # proves the retry actually happened


async def test_broken_pool_degrades_to_none_with_warning(cfg, tmp_path, caplog):
    Path(cfg["cv"]["pool"]).write_text("experiences: [")
    call, calls = _caller()
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 0
    assert any("pool" in r.message for r in caplog.records)


async def test_malformed_pool_entry_degrades_to_none_with_warning(cfg, caplog):
    # End-to-end degradation contract for the operator's most likely typo: a
    # stray '-' making an experience a bare string. Anything other than
    # PoolError here escapes prepare_application and kills the tool call.
    Path(cfg["cv"]["pool"]).write_text("experiences:\n  - just a string\n")
    call, calls = _caller()
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 0
    assert any("pool" in r.message for r in caplog.records)


async def test_a_job_without_an_id_degrades_to_none(cfg):
    # "never raises" is only total if a caller passing an id-less job dict
    # degrades instead of dying on int(job["id"]).
    call, calls = _caller()
    assert await ensure_tailored_cv({"title": "Eng"}, cfg, {}, call) is None
    assert calls["n"] == 0


# --- extra coverage beyond the brief's verbatim cases: other degrade/branch paths ---


async def test_missing_template_dir_degrades_to_none(cfg):
    del cfg["cv"]["template_dir"]
    call, calls = _caller()
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 0


async def test_missing_en_template_file_degrades_to_none(cfg, caplog):
    (Path(cfg["cv"]["template_dir"]) / "cv-template.en.tex").unlink()
    call, calls = _caller()
    assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 0
    assert any("cv-template.en.tex" in r.message for r in caplog.records)


async def test_pt_selection_with_pt_template_uses_it(cfg):
    pt_template = TEMPLATE.replace("BASE_SUMMARY: The base summary line", "BASE_SUMMARY: PT base")
    (Path(cfg["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(pt_template)
    pt_response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "S",
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(pt_response)
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled


async def test_pt_selection_without_pt_template_falls_back_to_en(cfg, caplog):
    pt_response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "S",
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = _caller(pt_response)
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    assert any("no PT template" in r.message for r in caplog.records)


async def test_existing_tex_retries_compile_and_succeeds(cfg):
    out = generated_dir_for(cfg, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = _caller()
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result == TailoredCV(out / "cv.pdf", True)
    assert calls["n"] == 0


async def test_existing_tex_retries_compile_and_stays_uncompiled(cfg):
    out = generated_dir_for(cfg, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=False),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result == TailoredCV(out / "cv.tex", False)
    assert calls["n"] == 0


async def test_a_wrong_shaped_llm_response_still_produces_a_cv(cfg):
    # End-to-end companion to test_generate's shape cases: a posting that
    # steers bullets_translated into a list must not turn prepare_application
    # into an error line where the whole sheet should be.
    resp = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "S",
            "technical_expertise": "T",
            "bullets": 3,
            "open_source": "oss",
            "bullets_translated": ["not a mapping"],
        }
    )
    call, calls = _caller(resp)
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    assert calls["n"] == 1
    # bullets degraded to empty, so the spec's fallback renders every pool bullet
    assert "Did A" in (generated_dir_for(cfg, 42) / "cv.tex").read_text()


# --- a .tex that cannot compile must never become a permanent cache hit -----


async def test_a_tex_that_cannot_compile_is_discarded_not_cached(cfg, caplog):
    # compile_pdf returning None means two different things. With pdflatex on
    # the machine it means THIS DOCUMENT does not compile — it will fail
    # identically forever, so keeping the .tex turns one unlucky generation
    # into a permanently broken tailored CV for this job.
    call, _ = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result is None  # degrades to the default CV, per the spec
    assert not (generated_dir_for(cfg, 42) / "cv.tex").exists()


async def test_three_consecutive_prepares_regenerate_instead_of_re_failing(cfg):
    # The measured bug: prepares 2 and 3 made ZERO llm calls and re-failed on
    # the cached .tex. Regeneration is what makes the failure transient.
    call, calls = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        for _ in range(3):
            assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert calls["n"] == 3


async def test_a_tex_kept_for_a_missing_latex_compiles_later_without_an_llm_call(cfg):
    # The legitimate case the short-circuit exists for, preserved end to end:
    # prepare 1 on a machine with no pdflatex keeps the .tex; prepare 2, after
    # latex is installed, compiles that same file and spends nothing.
    call, calls = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=False),
    ):
        first = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert first is not None and not first.compiled
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        second = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert second is not None and second.compiled
    assert calls["n"] == 1  # the second prepare reused the cached .tex


async def test_a_partial_pdf_left_by_a_failed_compile_is_discarded_with_the_tex(cfg):
    # A timeout SIGKILLs pdflatex mid-write, so a truncated cv.pdf survives on
    # disk while compile_pdf still returns None. Leaving it there is worse than
    # the bug round 5 fixed, because the cache short-circuits on cv.pdf BEFORE
    # any compile: every later prepare hands the operator a corrupt file at
    # zero LLM calls, with the source .tex already deleted. 12 tests in this
    # file patch compile_pdf and not one staged a .pdf beside it, which is why
    # the suite could not see this.
    def timeout_like(tex):
        # Exactly what a timeout does: pdflatex is SIGKILLed mid-write, so a
        # truncated .pdf is on disk while compile_pdf still answers None.
        tex.with_suffix(".pdf").write_bytes(b"%PDF-1.7\ntruncated, no EOF marker")

    call, calls = _caller()
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=timeout_like),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    out = generated_dir_for(cfg, 42)
    assert not (out / "cv.tex").exists()
    assert not (out / "cv.pdf").exists()  # the corrupt file must not survive
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        second = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert second is not None and second.compiled
    assert calls["n"] == 2  # one call per prepare: nothing was served from cache


async def test_spend_limit_is_swallowed_here(cfg, caplog):
    async def spend_limit_call(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session spend limit")

    result = await ensure_tailored_cv(JOB, cfg, {}, spend_limit_call)
    assert result is None
    assert any("spend limit" in r.message for r in caplog.records)


async def test_non_spend_limit_exception_reraises(cfg):
    # decide_cv's own contract only ever re-raises spend-limit exceptions (see
    # generate.py) — everything else it degrades to None internally. Exercising
    # service.py's own re-raise branch (any other exception is not ours to
    # swallow) requires patching decide_cv itself, not the caller.
    call, _ = _caller()
    with (
        patch(
            "moonlighter.application.cvgen.service.decide_cv",
            side_effect=RuntimeError("totally unrelated failure"),
        ),
        pytest.raises(RuntimeError, match="unrelated failure"),
    ):
        await ensure_tailored_cv(JOB, cfg, {}, call)


# --- shrink to one page ------------------------------------------------------

WIDE_POOL_YAML = """
experiences:
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
      - id: t-b
        angles: [backend]
        latex: 'Did B'
      - id: t-c
        angles: [backend]
        latex: 'Did C'
open_source:
  - id: oss-m
    angles: [ai]
    latex: 'moonlighter'
"""
WIDE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a", "t-b", "t-c"],
        "open_source": ["oss-m"],
    }
)


def _compiler_that_reports(pages_by_attempt):
    """A compile_pdf stand-in that writes a pdflatex-shaped log and a pdf,
    reporting the page count for each successive attempt."""
    attempts = {"n": 0}

    def compile_(tex):
        pages = pages_by_attempt[min(attempts["n"], len(pages_by_attempt) - 1)]
        attempts["n"] += 1
        tex.with_suffix(".log").write_text(f"Output written on cv.pdf ({pages} pages, 1 bytes).\n")
        tex.with_suffix(".pdf").write_bytes(b"%PDF")
        return tex.with_suffix(".pdf")

    return compile_, attempts


async def test_a_two_page_cv_is_shrunk_until_it_fits(cfg):
    Path(cfg["cv"]["pool"]).write_text(WIDE_POOL_YAML)
    call, calls = _caller(WIDE_GENERATE)
    compile_, attempts = _compiler_that_reports([2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    assert attempts["n"] == 3
    assert calls["n"] == 1  # shrinking never spends another LLM call
    tex = (generated_dir_for(cfg, 42) / "cv.tex").read_text()
    # dropped from the end, in the model's order: t-c first, then t-b
    assert "Did A" in tex and "Did B" not in tex and "Did C" not in tex
    assert "moonlighter" in tex  # open source survives while a bullet could go


async def test_open_source_goes_only_when_no_bullet_can(cfg):
    Path(cfg["cv"]["pool"]).write_text(WIDE_POOL_YAML)
    call, _ = _caller(WIDE_GENERATE)
    compile_, _attempts = _compiler_that_reports([2, 2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    tex = (generated_dir_for(cfg, 42) / "cv.tex").read_text()
    assert "Did A" in tex  # the experience keeps at least one bullet
    assert "moonlighter" not in tex


async def test_a_cv_that_never_fits_is_discarded_like_a_non_compiling_one(cfg, caplog):
    Path(cfg["cv"]["pool"]).write_text(WIDE_POOL_YAML)
    call, _ = _caller(WIDE_GENERATE)
    compile_, _attempts = _compiler_that_reports([2])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    out = generated_dir_for(cfg, 42)
    assert not (out / "cv.tex").exists() and not (out / "cv.pdf").exists()
    assert any("one page" in r.message for r in caplog.records)


async def test_a_cached_tex_that_compiles_to_two_pages_is_discarded(cfg):
    # The "machine gained latex" path has no selection to shrink; a cached
    # document that overflows is discarded so the next prepare regenerates
    # under the budget instead of serving two pages forever.
    out = generated_dir_for(cfg, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("stale tex")
    call, calls = _caller()
    compile_, _attempts = _compiler_that_reports([2])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, cfg, {}, call) is None
    assert not (out / "cv.tex").exists() and not (out / "cv.pdf").exists()
    assert calls["n"] == 0


async def test_no_page_count_is_accepted_as_is(cfg):
    # A compile_pdf that leaves no log (every existing test's stand-in) is
    # trusted: the log is evidence of overflow, its absence is not.
    call, _ = _caller()
    with patch(
        "moonlighter.application.cvgen.service.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled


PROSE_POOL_YAML = """
experiences:
  - id: p-a
    company: Nubank
    title: Staff
    period: "2020 -- 2023"
    location: SP
    prose: 'Led the platform team.'
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: t-a
        angles: [backend]
        latex: 'Did A'
      - id: t-b
        angles: [backend]
        latex: 'Did B'
      - id: t-c
        angles: [backend]
        latex: 'Did C'
"""
PROSE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["p-a", "t-a", "t-b", "t-c"],
        "open_source": [],
    }
)


async def test_a_prose_id_among_selected_bullets_is_never_dropped(cfg):
    # A prose id shares the "bullets" list with real experience bullets (it
    # carries a translation, per Task 3), but owns no experience of its own —
    # _shrunk's `bid in owner` guard must skip it while counting, not drop it.
    Path(cfg["cv"]["pool"]).write_text(PROSE_POOL_YAML)
    call, _ = _caller(PROSE_GENERATE)
    compile_, attempts = _compiler_that_reports([2, 1])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    assert attempts["n"] == 2
    tex = (generated_dir_for(cfg, 42) / "cv.tex").read_text()
    assert "Led the platform team" in tex  # the prose entry survives the shrink
    assert "Did C" not in tex  # the last experience bullet is what went


TWO_EXPERIENCE_POOL_YAML = """
experiences:
  - company: Nubank
    title: Staff
    period: "2020 -- 2023"
    location: SP
    bullets:
      - id: b-1
        angles: [backend]
        latex: 'B one'
      - id: b-2
        angles: [backend]
        latex: 'B two'
      - id: b-3
        angles: [backend]
        latex: 'B three'
  - company: Trybe
    title: Dev
    period: "2023 -- 2026"
    location: BH
    bullets:
      - id: a-1
        angles: [backend]
        latex: 'A only'
"""
# The model places A's single bullet LAST in its order — a global (non-per-
# experience) counter would treat it as "just the tail element" and drop it
# first, since it only checks whether MORE than one bullet remains selected
# overall, not whether it is A's or B's. The correct per-experience bookkeeping
# must skip it (A only has 1 selected) and keep dropping from B's tail instead.
TWO_EXPERIENCE_GENERATE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["b-1", "b-2", "b-3", "a-1"],
        "open_source": [],
    }
)


async def test_shrunk_bookkeeping_is_per_experience_not_global(cfg):
    # Reproduces the review finding: owner/selected_per_exp exist so that an
    # experience with few selected bullets (A, here down to its only one) is
    # never touched while another experience (B) still has more than one
    # selected. A constant/global key would instead drop from the END of the
    # whole selection.bullets list regardless of which experience owns it —
    # which here means dropping A's only bullet FIRST, since it sits last in
    # the model's order. Two clearly distinguishable bullet texts per
    # experience make a wrong implementation produce a detectably different
    # final .tex: "A only" would be missing and "B three" would survive.
    Path(cfg["cv"]["pool"]).write_text(TWO_EXPERIENCE_POOL_YAML)
    call, calls = _caller(TWO_EXPERIENCE_GENERATE)
    compile_, attempts = _compiler_that_reports([2, 2, 1])
    with (
        patch("moonlighter.application.cvgen.service.compile_pdf", side_effect=compile_),
        patch("moonlighter.application.cvgen.service.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert isinstance(result, TailoredCV) and result.compiled
    assert attempts["n"] == 3  # two shrinks were needed to reach one page
    assert calls["n"] == 1  # shrinking never spends another LLM call
    tex = (generated_dir_for(cfg, 42) / "cv.tex").read_text()
    # A's only bullet must never be touched: dropping it would zero out A's
    # selection while B still had more than one bullet selected.
    assert "A only" in tex
    # Both drops came from B's tail, in the model's order: "B three" first,
    # then "B two" — B still keeps its first bullet.
    assert "B one" in tex
    assert "B two" not in tex
    assert "B three" not in tex
