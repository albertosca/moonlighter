from moonlighter.application.cvgen.latex.compile import looks_like_a_compiled_pdf, page_count


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


def test_looks_like_a_compiled_pdf_accepts_a_real_compiled_pdf(tmp_path):
    # Real pdflatex output, byte-for-byte measured: a well-formed PDF's last
    # non-whitespace content is %%EOF, even with a trailing newline after it.
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.5\n...binary content...\nstartxref\n11120\n%%EOF\n")
    assert looks_like_a_compiled_pdf(pdf) is True


def test_looks_like_a_compiled_pdf_rejects_a_truncated_write(tmp_path):
    # Measured shape of a SIGKILLed compile (compile.py's own _discard_partial
    # docstring): a %PDF-1.7 header with no %%EOF, because pdflatex writes the
    # file incrementally and never got to finish it.
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 500)
    assert looks_like_a_compiled_pdf(pdf) is False


def test_looks_like_a_compiled_pdf_rejects_a_directory(tmp_path):
    # exists() alone is True for a directory named cv.pdf; the cache checks
    # this guards must not serve a directory as though it were a file.
    pdf = tmp_path / "cv.pdf"
    pdf.mkdir()
    assert looks_like_a_compiled_pdf(pdf) is False


def test_looks_like_a_compiled_pdf_rejects_a_missing_file(tmp_path):
    assert looks_like_a_compiled_pdf(tmp_path / "nope.pdf") is False


def test_looks_like_a_compiled_pdf_rejects_an_unreadable_file(tmp_path):
    # A permission error mid-read must degrade to "not trusted", the same as
    # every other way this file could be unusable — never propagate.
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.5\n...\n%%EOF\n")
    pdf.chmod(0o000)
    try:
        assert looks_like_a_compiled_pdf(pdf) is False
    finally:
        pdf.chmod(0o644)  # restore so tmp_path cleanup can remove it


def test_looks_like_a_compiled_pdf_finds_eof_even_in_a_large_file(tmp_path):
    # %%EOF sits in the LAST kilobyte of a real PDF regardless of the file's
    # total size (it is the final structural marker) — a naive "read it all"
    # implementation would also pass this, but a naive "read only the first
    # N bytes" implementation would wrongly reject it. Prove the tail is what
    # gets checked.
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.5\n" + b"x" * 50_000 + b"\nstartxref\n11120\n%%EOF\n")
    assert looks_like_a_compiled_pdf(pdf) is True
