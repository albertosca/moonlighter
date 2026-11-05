"""Shared pieces of the check_cv_pool_floor pins: a two-experience pool, the template and the stubbed compiler."""

import textwrap
from unittest.mock import patch

import check_cv_pool_floor

from moonlighter.application.cvgen.pool.loader import load_pool

POOL_YAML = textwrap.dedent("""\
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
      - company: AppProva
        title: Eng
        period: "2017 -- 2019"
        location: BH
        bullets:
          - id: a-a
            angles: [backend]
            latex: 'Did C'
    """)
TEMPLATE = (
    "%%BASE_SUMMARY: The base summary line\n"
    "%%BASE_EXPERTISE: Elixir, React\n"
    "\\cvlistitem{%%SUMMARY%%}\n\\cvlistitem{%%TECHNICAL_EXPERTISE%%}\n"
    "%%EXPERIENCE%%\n%%OPEN_SOURCE%%\n"
)


def pool(tmp_path):
    """The loaded POOL_YAML, written under tmp_path."""
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    return load_pool(pool_path)


def configuration(tmp_path, *, with_template=True):
    """A config whose cv.pool and cv.template_dir point at files under tmp_path."""
    pool_path = tmp_path / "cv-pool.yaml"
    pool_path.write_text(POOL_YAML)
    template_directory = tmp_path / "templates"
    template_directory.mkdir()
    if with_template:
        (template_directory / "cv-template.en.tex").write_text(TEMPLATE)
    return {"cv": {"pool": str(pool_path), "template_dir": str(template_directory)}}


def compiling(pages):
    """Patches that make pdflatex available, every compile succeed and the pdf count `pages`."""
    return (
        patch.object(check_cv_pool_floor, "latex_available", return_value=True),
        patch.object(
            check_cv_pool_floor, "compile_pdf", side_effect=lambda tex: tex.with_suffix(".pdf")
        ),
        patch.object(check_cv_pool_floor, "page_count", return_value=pages),
    )
