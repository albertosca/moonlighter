import json
from pathlib import Path
from unittest.mock import patch

import pytest
from moonlighter.application.cvgen.page_fit import TailoredCV
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.tailored_cv_samples import JOB, counting_caller, write_pool


async def test_generation_failure_degrades_to_none(config):
    call, _ = counting_caller("garbage")
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    # A transient malformed response must NOT write the permanent USE_BASE
    # marker — that would disable tailored-CV generation for this job forever.
    assert not (generated_dir_for(config, 42) / "USE_BASE").exists()
    good_call, good_calls = counting_caller()
    with patch(
        "moonlighter.application.cvgen.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        retry = await ensure_tailored_cv(JOB, config, {}, caller=good_call)
    assert isinstance(retry, TailoredCV)
    assert retry.compiled
    assert good_calls["n"] == 1  # proves the retry actually happened


async def test_broken_pool_degrades_to_none_with_warning(config, tmp_path, caplog):
    write_pool(config, "experiences: [")
    call, calls = counting_caller()
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 0
    assert any("pool" in record.message for record in caplog.records)


async def test_malformed_pool_entry_degrades_to_none_with_warning(config, caplog):
    # End-to-end degradation contract for the operator's most likely typo: a
    # stray '-' making an experience a bare string. Anything other than
    # PoolError here escapes prepare_application and kills the tool call.
    write_pool(config, "experiences:\n  - just a string\n")
    call, calls = counting_caller()
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 0
    assert any("pool" in record.message for record in caplog.records)


async def test_a_job_without_an_id_degrades_to_none(config):
    # "never raises" is only total if a caller passing an id-less job dict
    # degrades instead of dying on int(job["id"]).
    call, calls = counting_caller()
    assert await ensure_tailored_cv({"title": "Eng"}, config, {}, caller=call) is None
    assert calls["n"] == 0


async def test_missing_template_dir_degrades_to_none(config):
    del config["cv"]["template_dir"]
    call, calls = counting_caller()
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 0


async def test_missing_en_template_file_degrades_to_none(config, caplog):
    (Path(config["cv"]["template_dir"]) / "cv-template.en.tex").unlink()
    call, calls = counting_caller()
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert calls["n"] == 0
    assert any("cv-template.en.tex" in record.message for record in caplog.records)


async def test_a_wrong_shaped_llm_response_still_produces_a_cv(config):
    # End-to-end companion to test_generate's shape cases: a posting that
    # steers bullets_translated into a list must not turn prepare_application
    # into an error line where the whole sheet should be.
    response = json.dumps(
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
    call, calls = counting_caller(response)
    with patch(
        "moonlighter.application.cvgen.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    assert calls["n"] == 1
    # bullets degraded to empty, so the spec's fallback renders every pool bullet
    assert "Did A" in (generated_dir_for(config, 42) / "cv.tex").read_text()


async def test_spend_limit_is_swallowed_here(config, caplog):
    async def spend_limit_call(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session spend limit")

    result = await ensure_tailored_cv(JOB, config, {}, caller=spend_limit_call)
    assert result is None
    assert any("spend limit" in record.message for record in caplog.records)


async def test_non_spend_limit_exception_reraises(config):
    # decide_cv's own contract only ever re-raises spend-limit exceptions (see
    # generate.py) — everything else it degrades to None internally. Exercising
    # service.py's own re-raise branch (any other exception is not ours to
    # swallow) requires patching decide_cv itself, not the caller.
    call, _ = counting_caller()
    with (
        patch(
            "moonlighter.application.cvgen.service.decide_cv",
            side_effect=RuntimeError("totally unrelated failure"),
        ),
        pytest.raises(RuntimeError, match="unrelated failure"),
    ):
        await ensure_tailored_cv(JOB, config, {}, caller=call)
