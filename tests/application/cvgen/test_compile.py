import subprocess
from unittest.mock import MagicMock, patch

import pytest
from moonlighter.application.cvgen.compile import compile_pdf, latex_available, page_count


def test_latex_available_reports_whether_the_machine_can_compile():
    # service._after_compile reads a failed compile through this: with no
    # pdflatex the failure says nothing about the document (keep the .tex),
    # with pdflatex present it says the document is broken (discard it). A
    # function stuck on one answer would silently pick one of those forever.
    with patch("moonlighter.application.cvgen.compile.shutil.which", return_value=None):
        assert latex_available() is False
    with patch(
        "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
    ):
        assert latex_available() is True


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
    # Verify command contract: args and kwargs
    expected_cmd = ["/usr/bin/pdflatex", "-interaction=nonstopmode", "-halt-on-error", "cv.tex"]
    assert run.call_args.args[0] == expected_cmd
    assert run.call_args.kwargs["cwd"] == tmp_path
    assert run.call_args.kwargs["capture_output"] is True
    assert run.call_args.kwargs["timeout"] == 120


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
    # Verify command contract even on failure
    expected_cmd = ["/usr/bin/pdflatex", "-interaction=nonstopmode", "-halt-on-error", "cv.tex"]
    assert run.call_args.args[0] == expected_cmd
    assert run.call_args.kwargs["timeout"] == 120


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


def test_custom_timeout_reaches_subprocess(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    run = MagicMock(return_value=MagicMock(returncode=0))
    custom_timeout = 300
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        (tmp_path / "cv.pdf").write_bytes(b"%PDF")
        compile_pdf(tex, timeout_s=custom_timeout)
    # Verify custom timeout reaches subprocess.run on both passes
    assert run.call_args.kwargs["timeout"] == custom_timeout


def test_a_failed_compile_removes_a_partial_pdf(tmp_path):
    # pdflatex writes the PDF incrementally, so a run that dies partway leaves
    # a truncated file. compile_pdf spawned it, so it clears it: a compile that
    # did not succeed must leave no PDF for any caller to serve.
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    partial = tmp_path / "cv.pdf"
    partial.write_bytes(b"%PDF-1.7\ntruncated, no EOF marker")
    run = MagicMock(return_value=MagicMock(returncode=1))
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert not partial.exists()
    assert tex.exists()  # the source is the caller's to keep or discard


def test_a_timed_out_compile_removes_a_partial_pdf(tmp_path):
    # The measured case: subprocess.run SIGKILLs pdflatex on timeout, so it
    # never gets to clean up after itself.
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    partial = tmp_path / "cv.pdf"
    partial.write_bytes(b"%PDF-1.7\ntruncated, no EOF marker")
    run = MagicMock(side_effect=subprocess.TimeoutExpired("pdflatex", 120))
    with (
        patch(
            "moonlighter.application.cvgen.compile.shutil.which", return_value="/usr/bin/pdflatex"
        ),
        patch("moonlighter.application.cvgen.compile.subprocess.run", run),
    ):
        assert compile_pdf(tex) is None
    assert not partial.exists()


@pytest.mark.e2e
def test_real_pdflatex_compiles_a_minimal_document(tmp_path):
    import shutil as real_shutil

    if real_shutil.which("pdflatex") is None:
        pytest.skip("pdflatex not installed")
    tex = tmp_path / "cv.tex"
    tex.write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
    pdf = compile_pdf(tex)
    assert pdf is not None and pdf.read_bytes()[:4] == b"%PDF"


def test_page_count_reads_the_pdflatex_log(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    (tmp_path / "cv.log").write_text(
        "This is pdfTeX\nOutput written on cv.pdf (2 pages, 205028 bytes).\nTranscript written on cv.log.\n"
    )
    assert page_count(tex) == 2


def test_page_count_handles_the_singular_form(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    (tmp_path / "cv.log").write_text("Output written on cv.pdf (1 page, 195857 bytes).\n")
    assert page_count(tex) == 1


def test_page_count_is_none_without_a_log_or_without_the_line(tmp_path):
    tex = tmp_path / "cv.tex"
    tex.write_text("x")
    assert page_count(tex) is None
    (tmp_path / "cv.log").write_text("! Emergency stop.\nNo pages of output.\n")
    assert page_count(tex) is None
