import json
from unittest.mock import patch

from moonlighter.application.cvgen.latex.page_fit import TailoredCV
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.tailored_cv_samples import GENERATE, JOB, counting_caller


async def test_no_pool_configured_is_none_without_calls(tmp_path):
    call, calls = counting_caller()
    assert await ensure_tailored_cv(JOB, {"cv": {}}, {}, caller=call) is None
    assert calls["n"] == 0


async def test_generates_writes_tex_and_compiles(config):
    call, _ = counting_caller()
    with patch(
        "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    out = generated_dir_for(config, 42)
    assert (out / "cv.tex").exists()
    assert "Did A" in (out / "cv.tex").read_text()
    assert "The base summary line" not in (out / "cv.tex").read_text()  # markers stripped


async def test_use_base_writes_marker_and_skips_next_time(config):
    call, calls = counting_caller(json.dumps({"decision": "USE_BASE"}))
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert (generated_dir_for(config, 42) / "USE_BASE").exists()
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 1  # second call served by the marker


async def test_existing_pdf_short_circuits(config):
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.pdf").write_bytes(b"%PDF-1.5\n...\n%%EOF\n")  # real-shaped, not just any bytes
    call, calls = counting_caller()
    result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert result == TailoredCV(out / "cv.pdf", compiled=True)
    assert calls["n"] == 0  # the no-LLM-call-on-cache-hit contract


async def test_a_truncated_cached_pdf_is_not_trusted(config):
    # round-6 finding: exists() alone would serve this forever at zero LLM
    # calls. A SIGKILL of moonlighter itself between pdflatex's exit and the
    # next cache check can strand exactly this shape (measured in
    # compile.py's _discard_partial docstring): a %PDF header, no %%EOF.
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.pdf").write_bytes(b"%PDF-1.7\n" + b"\x00" * 500)
    call, calls = counting_caller(GENERATE)
    with (
        patch(
            "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    # Regenerates instead of serving the truncated file — proves the cache
    # check does not just skip the bad file, it treats it as a real miss.
    assert calls["n"] == 1
    assert result is not None


async def test_a_directory_named_cv_pdf_is_not_trusted(config):
    # exists() is True for a directory too; the cache check must not try to
    # open one as a file.
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.pdf").mkdir()
    call, calls = counting_caller(GENERATE)
    with (
        patch(
            "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
            side_effect=lambda tex: tex.with_suffix(".pdf"),
        ),
        patch("moonlighter.application.cvgen.latex.page_fit.latex_available", return_value=True),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert calls["n"] == 1
    assert result is not None


async def test_ensure_tailored_cv_is_still_off_with_no_config_and_no_bootstrapped_file(
    monkeypatch, tmp_path
):
    # The default path existing as a CONCEPT must not turn the feature on by
    # itself -- only an actual file at that path does (nothing ever calls the
    # bootstrap in this test).
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    result = await ensure_tailored_cv(JOB, {}, {}, caller=counting_caller())
    assert result is None
