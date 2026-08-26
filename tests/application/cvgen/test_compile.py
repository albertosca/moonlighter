import subprocess
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.application.cvgen.compile import compile_pdf


def test_no_pdflatex_returns_none(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    with patch("moonlighter.application.cvgen.compile.shutil.which", return_value=None):
        assert compile_pdf(tex) is None


def test_runs_two_passes_in_the_tex_dir(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(return_value=MagicMock(returncode=0))
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        (tmp_path / "cv.pdf").write_bytes(b"%PDF")  # what a successful run leaves
        result = compile_pdf(tex)
    assert result == tmp_path / "cv.pdf"
    assert run.call_count == 2
    assert run.call_args.kwargs["cwd"] == tmp_path


def test_failed_compile_returns_none_keeps_tex(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(return_value=MagicMock(returncode=1))
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert tex.exists()


def test_timeout_returns_none_keeps_tex(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(side_effect=subprocess.TimeoutExpired("pdflatex", 120))
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert tex.exists()


@pytest.mark.e2e
def test_real_pdflatex_compiles_a_minimal_document(tmp_path):
    import shutil as real_shutil

    if real_shutil.which("pdflatex") is None:
        pytest.skip("pdflatex not installed")
    tex = tmp_path / "cv.tex"
    tex.write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
    pdf = compile_pdf(tex)
    assert pdf is not None and pdf.read_bytes()[:4] == b"%PDF"
