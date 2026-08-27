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
    assert calls["n"] == 0


async def test_no_latex_returns_tex_uncompiled(cfg):
    call, _ = _caller()
    with patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None):
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
    with patch("moonlighter.application.cvgen.service.compile_pdf", return_value=None):
        result = await ensure_tailored_cv(JOB, cfg, {}, call)
    assert result == TailoredCV(out / "cv.tex", False)
    assert calls["n"] == 0


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
