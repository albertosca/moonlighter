from pathlib import Path

import pytest
from moonlighter.application.answers.cv import CVNotFoundError, resolve_cv_path


def test_resolve_cv_path_uses_company_specific(tmp_path):
    nubank_cv = tmp_path / "nu.pdf"
    nubank_cv.write_bytes(b"x")
    default_cv = tmp_path / "def.pdf"
    default_cv.write_bytes(b"x")
    config = {"cv": {"default": str(default_cv), "by_company": {"nubank": str(nubank_cv)}}}
    assert resolve_cv_path("nubank", config) == str(nubank_cv)


def test_resolve_cv_path_falls_back_to_default(tmp_path):
    default_cv = tmp_path / "def.pdf"
    default_cv.write_bytes(b"x")
    config = {"cv": {"default": str(default_cv), "by_company": {"nubank": "x.pdf"}}}
    assert resolve_cv_path("stripe", config) == str(default_cv)


def test_resolve_cv_path_company_match_is_case_insensitive(tmp_path):
    cv = tmp_path / "nu.pdf"
    cv.write_bytes(b"x")
    default_cv = tmp_path / "def.pdf"
    default_cv.write_bytes(b"x")
    config = {"cv": {"default": str(default_cv), "by_company": {"nubank": str(cv)}}}
    assert resolve_cv_path("Nubank", config) == str(cv)


def test_resolve_cv_path_raises_when_mapped_file_missing(tmp_path):
    config = {"cv": {"default": str(tmp_path / "missing.pdf"), "by_company": {}}}
    with pytest.raises(CVNotFoundError):
        resolve_cv_path("stripe", config)


def test_resolve_cv_path_raises_when_no_mapping_and_no_default():
    with pytest.raises(CVNotFoundError):
        resolve_cv_path("stripe", {"cv": {"by_company": {}}})


def test_resolve_cv_path_relative_resolved_from_moonlighter_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MOONLIGHTER_HOME", str(tmp_path))
    cv_file = tmp_path / "cvs" / "general.pdf"
    cv_file.parent.mkdir(parents=True)
    cv_file.write_bytes(b"x")
    config = {"cv": {"default": "cvs/general.pdf"}}
    from moonlighter.core.config import moonlighter_home

    result = resolve_cv_path("stripe", config)
    assert result == str(moonlighter_home() / "cvs" / "general.pdf")
    assert Path(result).exists()


def _tailored_config(tmp_path):
    company_cv = tmp_path / "nu.pdf"
    company_cv.write_bytes(b"x")
    default_cv = tmp_path / "def.pdf"
    default_cv.write_bytes(b"x")
    return {
        "cv": {
            "default": str(default_cv),
            "by_company": {"nubank": str(company_cv)},
            "generated_dir": str(tmp_path / "generated"),
        }
    }, company_cv


def test_job_generated_pdf_wins_over_company_and_default(tmp_path):
    config, _ = _tailored_config(tmp_path)
    generated = tmp_path / "generated" / "42"
    generated.mkdir(parents=True)
    (generated / "cv.pdf").write_bytes(b"%PDF-1.5\n...\n%%EOF\n")  # real-shaped
    assert resolve_cv_path("nubank", config, job_id=42) == str(generated / "cv.pdf")


def test_a_truncated_generated_pdf_falls_through_to_company_cv(tmp_path):
    # round-6 finding: exists() alone would resolve to the truncated file and
    # upload it. A stranded partial-write (compile.py's own _discard_partial
    # docstring shape: %PDF header, no %%EOF) must degrade the same way a
    # missing file already does — fall through to the company/default CV.
    config, company_cv = _tailored_config(tmp_path)
    generated = tmp_path / "generated" / "42"
    generated.mkdir(parents=True)
    (generated / "cv.pdf").write_bytes(b"%PDF-1.7\n" + b"\x00" * 500)
    assert resolve_cv_path("nubank", config, job_id=42) == str(company_cv)


def test_a_directory_named_cv_pdf_falls_through_to_company_cv(tmp_path):
    config, company_cv = _tailored_config(tmp_path)
    generated = tmp_path / "generated" / "42"
    generated.mkdir(parents=True)
    (generated / "cv.pdf").mkdir()
    assert resolve_cv_path("nubank", config, job_id=42) == str(company_cv)


def test_tex_only_generated_dir_does_not_win(tmp_path):
    # Nothing uploadable in a tex-only dir — the sheet's compile note covers it.
    config, company_cv = _tailored_config(tmp_path)
    generated = tmp_path / "generated" / "42"
    generated.mkdir(parents=True)
    (generated / "cv.tex").write_text("x")
    assert resolve_cv_path("nubank", config, job_id=42) == str(company_cv)


def test_no_job_id_keeps_todays_behavior(tmp_path):
    config, company_cv = _tailored_config(tmp_path)
    assert resolve_cv_path("nubank", config) == str(company_cv)


def test_tilde_in_cv_default_expands_like_the_tailored_cv_keys(monkeypatch, tmp_path):
    # Before: "~/cvs/x.pdf" became "<MOONLIGHTER_HOME>/~/cvs/x.pdf" while the
    # three cv.* keys next to it expanded "~". One convention for the block.
    monkeypatch.setenv("HOME", str(tmp_path))
    cv = tmp_path / "cvs" / "x.pdf"
    cv.parent.mkdir()
    cv.write_bytes(b"%PDF")
    assert resolve_cv_path("acme", {"cv": {"default": "~/cvs/x.pdf"}}) == str(cv)
