import pytest

from candidatador.applicator.cv import CVNotFoundError, resolve_cv_path


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
