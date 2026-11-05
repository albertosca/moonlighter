"""A compile_pdf stand-in for the tests that exercise the one-page fit."""


def compiler_that_reports(pages_by_attempt):
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
