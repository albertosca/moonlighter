import json
from pathlib import Path
from unittest.mock import patch

import pytest
from moonlighter.application.cvgen.latex.page_fit import TailoredCV
from moonlighter.application.cvgen.paths import generated_dir_for
from moonlighter.application.cvgen.service import ensure_tailored_cv

from tests.application.cvgen.log_records import logged_warnings
from tests.application.cvgen.tailored_cv_samples import (
    GENERATE_PORTUGUESE,
    JOB,
    TEMPLATE,
    counting_caller,
    fixed_caller,
)

PAGE_FIT = "moonlighter.application.cvgen.latex.page_fit"


@pytest.fixture
def config_with_baseless_portuguese_template(config):
    (Path(config["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(
        "\\cvlistitem{%%SUMMARY%%}\n%%EXPERIENCE%%\n"
    )
    return config


async def test_pt_selection_with_pt_template_uses_it(config):
    pt_template = TEMPLATE.replace("BASE_SUMMARY: The base summary line", "BASE_SUMMARY: PT base")
    (Path(config["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(pt_template)
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
    call, _ = counting_caller(pt_response)
    with patch(
        "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled


async def test_pt_selection_without_pt_template_falls_back_to_en(config, caplog):
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
    call, _ = counting_caller(pt_response)
    with patch(
        "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    assert any("no PT template" in record.message for record in caplog.records)


async def test_pt_non_typesettable_summary_falls_back_to_the_pt_base_not_english(config):
    # Finding 1: the base text parsed before decide_cv knows the language is
    # always English (service.py parses it out of en_template up front, for
    # the prompt). A non-typesettable field falls back to base text in the
    # RENDERED CV, so a PT posting whose model summary carries one
    # non-Latin glyph must not ship an English summary paragraph glued onto a
    # Portuguese CV.
    pt_template = TEMPLATE.replace(
        "BASE_SUMMARY: The base summary line", "BASE_SUMMARY: Resumo base PT"
    )
    (Path(config["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(pt_template)
    pt_response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Entrega rapido \U0001f680 todo sprint",  # non-Latin glyph -> fallback
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = counting_caller(pt_response)
    with patch(
        "moonlighter.application.cvgen.latex.page_fit.compile_pdf",
        side_effect=lambda tex: tex.with_suffix(".pdf"),
    ):
        result = await ensure_tailored_cv(JOB, config, {}, caller=call)
    assert isinstance(result, TailoredCV)
    assert result.compiled
    tex = generated_dir_for(config, 42).joinpath("cv.tex").read_text()
    assert "Resumo base PT" in tex
    assert "The base summary line" not in tex


async def test_pt_fallback_with_no_pt_base_to_replace_it_degrades_to_none(config, caplog):
    # The PT template exists but was authored without a %%BASE_SUMMARY marker
    # — there is no language-correct base to substitute, so the whole CV
    # degrades rather than shipping the English fallback anyway.
    pt_template = TEMPLATE.replace("%%BASE_SUMMARY: The base summary line\n", "")
    (Path(config["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(pt_template)
    pt_response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "Entrega rapido \U0001f680 todo sprint",  # non-Latin glyph -> fallback
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    call, _ = counting_caller(pt_response)
    assert await ensure_tailored_cv(JOB, config, {}, caller=call) is None
    assert any("no pt base" in record.message for record in caplog.records)


async def test_a_missing_portuguese_template_warns_before_rendering_in_english(config, caplog):
    with patch(f"{PAGE_FIT}.compile_pdf", side_effect=lambda tex: tex.with_suffix(".pdf")):
        await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(GENERATE_PORTUGUESE))
    assert logged_warnings(caplog) == ["no PT template — rendering the tailored CV in English"]


async def test_a_portuguese_selection_with_no_portuguese_base_names_the_language(
    config_with_baseless_portuguese_template, caplog
):
    config = config_with_baseless_portuguese_template
    response = json.dumps(
        {
            "decision": "GENERATE",
            "language": "pt",
            "summary": "The base summary line",
            "technical_expertise": "T",
            "bullets": ["t-a"],
            "open_source": [],
        }
    )
    assert await ensure_tailored_cv(JOB, config, {}, caller=fixed_caller(response)) is None
    assert logged_warnings(caplog) == [
        (
            "cv summary/expertise fell back to English base with no pt base to replace it — "
            "using default CV"
        )
    ]
