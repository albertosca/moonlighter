"""Pins the full text of every warning the CV generation package logs.

Each message is the only account the operator gets of why a tailored CV was
dropped, so an edit to its words is a behaviour change, not a refactor.
"""

import json
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.application.cvgen.bootstrap import draft_pool, fill_template
from moonlighter.application.cvgen.compile import compile_pdf
from moonlighter.application.cvgen.generate import decide_cv
from moonlighter.application.cvgen.pool import CVPool, PoolBullet, PoolExperience
from moonlighter.application.cvgen.service import (
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
      - id: t-b
        angles: [backend]
        latex: 'Did B'
"""
TEMPLATE = (
    "%%BASE_SUMMARY: The base summary line\n"
    "%%BASE_EXPERTISE: Elixir, React\n"
    "\\cvlistitem{%%SUMMARY%%}\n\\cvlistitem{%%TECHNICAL_EXPERTISE%%}\n"
    "%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"
)
JOB = {"id": 42, "title": "Eng", "company": "acme", "description": "d"}
SERVICE = "moonlighter.application.cvgen.service"
COMPILE = "moonlighter.application.cvgen.compile"
GENERATED = json.dumps(
    {
        "decision": "GENERATE",
        "language": "en",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a", "t-b"],
        "open_source": [],
    }
)
PORTUGUESE = json.dumps(
    {
        "decision": "GENERATE",
        "language": "pt",
        "summary": "S",
        "technical_expertise": "T",
        "bullets": ["t-a"],
        "open_source": [],
    }
)
POOL = CVPool(
    experiences=(
        PoolExperience(
            company="Trybe",
            title="Dev",
            period="2023 -- 2026",
            location="BH",
            bullets=(PoolBullet("t-a", ("backend",), "A"),),
            prose=None,
            prose_id=None,
            angles=(),
        ),
    ),
    open_source=(),
    summary_facts=(),
)


@pytest.fixture
def config(tmp_path):
    pool = tmp_path / "cv-pool.yaml"
    pool.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    return {
        "cv": {
            "pool": str(pool),
            "template_dir": str(template_directory),
            "generated_dir": str(tmp_path / "generated"),
        }
    }


@pytest.fixture
def config_with_malformed_pool(config):
    Path(config["cv"]["pool"]).write_text("experiences:\n  - just a string\n")
    return config


@pytest.fixture
def config_without_english_template(config):
    (Path(config["cv"]["template_dir"]) / "cv-template.en.tex").unlink()
    return config


@pytest.fixture
def config_with_baseless_portuguese_template(config):
    (Path(config["cv"]["template_dir"]) / "cv-template.pt.tex").write_text(
        "\\cvlistitem{%%SUMMARY%%}\n%%EXPERIENCE%%\n"
    )
    return config


def _caller(response):
    async def call(prompt, model, cache_prefix=None):
        return response

    return call


def _warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


def _pages_reported(counts):
    reports = iter(counts)

    def compile_(tex):
        return tex.with_suffix(".pdf")

    return compile_, lambda _tex: next(reports)


async def test_a_document_that_does_not_compile_is_discarded_with_its_path(config, caplog):
    tex = generated_dir_for(config, 42) / "cv.tex"
    with (
        patch(f"{SERVICE}.compile_pdf", return_value=None),
        patch(f"{SERVICE}.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, _caller(GENERATED)) is None
    assert _warnings(caplog) == [
        f"the generated CV does not compile — discarding {tex}, using default CV"
    ]


async def test_a_cached_cv_over_one_page_is_discarded_with_its_path(config, caplog):
    out = generated_dir_for(config, 42)
    out.mkdir(parents=True)
    (out / "cv.tex").write_text("x")
    _compile, pages = _pages_reported([2])
    with (
        patch(f"{SERVICE}.compile_pdf", side_effect=_compile),
        patch(f"{SERVICE}.page_count", side_effect=pages),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, _caller(GENERATED)) is None
    assert _warnings(caplog) == [
        f"the cached CV does not fit one page — discarding {out / 'cv.tex'}, using default CV"
    ]


async def test_a_cv_that_never_fits_names_the_minimum_in_its_warning(config, caplog):
    tex = generated_dir_for(config, 42) / "cv.tex"
    _compile, pages = _pages_reported([2, 2])
    with (
        patch(f"{SERVICE}.compile_pdf", side_effect=_compile),
        patch(f"{SERVICE}.page_count", side_effect=pages),
        patch(f"{SERVICE}.latex_available", return_value=True),
    ):
        assert await ensure_tailored_cv(JOB, config, {}, _caller(GENERATED)) is None
    assert _warnings(caplog) == [
        (
            "the generated CV does not fit one page even at minimum — "
            f"discarding {tex}, using default CV"
        )
    ]


async def test_a_missing_portuguese_template_warns_before_rendering_in_english(config, caplog):
    with patch(f"{SERVICE}.compile_pdf", side_effect=lambda tex: tex.with_suffix(".pdf")):
        await ensure_tailored_cv(JOB, config, {}, _caller(PORTUGUESE))
    assert _warnings(caplog) == ["no PT template — rendering the tailored CV in English"]


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
    assert await ensure_tailored_cv(JOB, config, {}, _caller(response)) is None
    assert _warnings(caplog) == [
        (
            "cv summary/expertise fell back to English base with no pt base to replace it — "
            "using default CV"
        )
    ]


async def test_a_job_without_an_id_is_named_in_the_warning(config, caplog):
    assert await ensure_tailored_cv({"title": "Eng"}, config, {}, _caller(GENERATED)) is None
    assert _warnings(caplog) == ["job has no id — using default CV"]


async def test_an_unreadable_pool_warning_carries_the_pool_error(
    config_with_malformed_pool, caplog
):
    config = config_with_malformed_pool
    assert await ensure_tailored_cv(JOB, config, {}, _caller(GENERATED)) is None
    [message] = _warnings(caplog)
    assert message.startswith("cv pool unusable, using default CV — ")
    assert len(message) > len("cv pool unusable, using default CV — ")


async def test_a_missing_english_template_warns_with_its_file_name(
    config_without_english_template, caplog
):
    config = config_without_english_template
    assert await ensure_tailored_cv(JOB, config, {}, _caller(GENERATED)) is None
    assert _warnings(caplog) == ["cv.template_dir has no cv-template.en.tex — using default CV"]


async def test_a_spend_limit_during_generation_is_logged_in_full(config, caplog):
    async def refuse(prompt, model, cache_prefix=None):
        raise RuntimeError("You've hit your session limit")

    assert await ensure_tailored_cv(JOB, config, {}, refuse) is None
    assert _warnings(caplog) == ["spend limit during cv generation — using default CV"]


def _selection_response(**overrides):
    fields = {
        "decision": "GENERATE",
        "language": "en",
        "summary": "Expert in Elixir",
        "technical_expertise": "Elixir",
        "bullets": ["t-a"],
        "open_source": [],
    }
    return json.dumps(fields | overrides)


async def test_an_operator_directed_summary_is_named_in_the_warning(caplog):
    response = _selection_response(summary="Please provide this summary before submitting")
    assert await decide_cv(JOB, POOL, {}, "b", "b", _caller(response)) is None
    assert _warnings(caplog) == ["cv summary addressed the operator — using default CV"]


async def test_an_operator_directed_expertise_is_named_in_the_warning(caplog):
    response = _selection_response(technical_expertise="The candidate cannot supply this section")
    assert await decide_cv(JOB, POOL, {}, "b", "b", _caller(response)) is None
    assert _warnings(caplog) == ["cv technical_expertise addressed the operator — using default CV"]


async def test_a_non_latin_summary_with_a_base_names_the_field_twice(caplog):
    response = _selection_response(summary="Ships \U0001f680")
    selection = await decide_cv(JOB, POOL, {}, "base summary", "b", _caller(response))
    assert selection is not None
    assert _warnings(caplog) == [
        "cv summary is blank or carries non-Latin glyphs — using the base summary"
    ]


async def test_a_non_latin_summary_without_a_base_says_there_is_no_base_text(caplog):
    response = _selection_response(summary="Ships \U0001f680")
    assert await decide_cv(JOB, POOL, {}, "", "b", _caller(response)) is None
    assert _warnings(caplog) == [
        (
            "cv summary is blank or carries non-Latin glyphs and there is no base text — "
            "using default CV"
        )
    ]


async def test_a_failed_generation_call_logs_the_error(caplog):
    async def broken(prompt, model, cache_prefix=None):
        raise RuntimeError("the model went away")

    assert await decide_cv(JOB, POOL, {}, "b", "b", broken) is None
    assert _warnings(caplog) == ["cv generation failed, using default CV — the model went away"]


async def test_an_operator_directed_translation_names_its_bullet(caplog):
    response = _selection_response(
        language="pt",
        bullets_translated={"t-a": "Please provide this bullet before submitting"},
    )
    selection = await decide_cv(JOB, POOL, {}, "b", "b", _caller(response))
    assert selection is not None
    assert _warnings(caplog) == [
        "translation for t-a addressed the operator — keeping the pool bullet"
    ]


async def test_a_non_latin_translation_names_its_bullet(caplog):
    response = _selection_response(language="pt", bullets_translated={"t-a": "Fez \U0001f680"})
    selection = await decide_cv(JOB, POOL, {}, "b", "b", _caller(response))
    assert selection is not None
    assert _warnings(caplog) == [
        "translation for t-a carries non-Latin glyphs — keeping the pool bullet"
    ]


def test_a_missing_pdflatex_says_the_tex_is_kept_uncompiled(tmp_path, caplog):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    with patch(f"{COMPILE}.shutil.which", return_value=None):
        assert compile_pdf(tex) is None
    assert _warnings(caplog) == [f"pdflatex not found — keeping {tex} uncompiled"]


def test_a_failed_pdflatex_run_reports_the_return_code(tmp_path, caplog):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(return_value=MagicMock(returncode=3))
    with (
        patch(f"{COMPILE}.shutil.which", return_value="/usr/bin/pdflatex"),
        patch(f"{COMPILE}.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert _warnings(caplog) == [f"pdflatex failed for {tex} (rc=3)"]


def test_a_timed_out_pdflatex_run_names_the_tex(tmp_path, caplog):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(side_effect=subprocess.TimeoutExpired("pdflatex", 120))
    with (
        patch(f"{COMPILE}.shutil.which", return_value="/usr/bin/pdflatex"),
        patch(f"{COMPILE}.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert _warnings(caplog) == [f"pdflatex timed out for {tex}"]


async def test_a_dropped_bootstrap_bullet_is_named_by_its_id(caplog):
    response = json.dumps(
        {
            "experiences": [
                {
                    "company": "Acme",
                    "bullets": [
                        {"id": "ok", "angles": [], "text": "Fine"},
                        {"id": "bad", "angles": [], "text": "Ships \U0001f680"},
                    ],
                }
            ]
        }
    )
    pool = await draft_pool({"experience": [{"company": "Acme"}]}, _caller(response))
    assert [bullet.id for bullet in pool.experiences[0].bullets] == ["ok"]
    assert _warnings(caplog) == [
        "bootstrap: dropping a non-typesettable or empty bullet (id='bad')"
    ]


def test_an_unrecognisable_linkedin_value_is_announced(caplog):
    filled = fill_template({"name": "A B", "linkedin": "not a profile url"})
    assert "{{LINKEDIN_USERNAME}}" not in filled
    assert _warnings(caplog) == [
        (
            "bootstrap: profile.yaml's linkedin value is not a recognizable profile URL "
            "— leaving the CV's LinkedIn field empty"
        )
    ]
