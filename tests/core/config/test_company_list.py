import pytest
from moonlighter.core.config import ConfigError, load_company_list


def test_load_company_list(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("""
greenhouse:
  - stripe
  - linear
lever:
  - gitlab
""")
    company_list = load_company_list(path=str(company_file))
    assert company_list["greenhouse"] == ["stripe", "linear"]
    assert company_list["lever"] == ["gitlab"]


def test_load_company_list_nonexistent():
    # If file doesn't exist, return empty dict
    company_list = load_company_list(path="/nonexistent/path.yaml")
    assert company_list == {}


def test_load_company_list_empty_yaml(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("")
    result = load_company_list(path=str(company_file))
    assert result == {}


def test_load_company_list_multiple_sources(tmp_path):
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("""
greenhouse:
  - stripe
lever:
  - gitlab
ashby:
  - notion
""")
    result = load_company_list(path=str(company_file))
    for key in ("greenhouse", "lever", "ashby"):
        assert key in result, f"key '{key}' missing from company list"


def test_load_company_list_mixed_value_shapes(tmp_path):
    """A phase-dict with a non-list value is ignored; a scalar value becomes [] (125->124, 129)."""
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text(
        "greenhouse:\n"
        "  phase1:\n"
        "    - stripe\n"
        "  phase_bad: not_a_list\n"
        "lever: 42\n"  # valor escalar (nem lista nem dict)
    )
    result = load_company_list(path=str(company_file))  # phase=None → concatena
    assert result["greenhouse"] == ["stripe"]
    assert result["lever"] == []


def test_load_company_list_with_phase_filter(tmp_path):
    """When phase is specified, returns only that phase's slugs."""
    company_file = tmp_path / "company_list.yaml"
    company_file.write_text("greenhouse:\n  phase1:\n    - stripe\n  phase2:\n    - linear\n")
    result = load_company_list(path=str(company_file), phase="phase1")
    assert result["greenhouse"] == ["stripe"]


def test_company_list_rejects_non_list_phase_value(tmp_path):
    """MINOR regression: a phase filter selecting a scalar phase value (not a
    list) must raise, not silently iterate the string character-by-character
    -- every single character is a str, so entry-level validation alone would
    pass and single-char slugs would get scanned."""
    path = tmp_path / "company_list.yaml"
    path.write_text("greenhouse:\n  phase1: notalist\n")
    with pytest.raises(ConfigError, match=r"greenhouse.*did not resolve to a list"):
        load_company_list(path, phase="phase1")


def test_company_list_rejects_non_string_entry(tmp_path):
    path = tmp_path / "company_list.yaml"
    path.write_text("greenhouse:\n  - nubank\n  - 42\n")
    with pytest.raises(ConfigError, match=r"greenhouse.*42"):
        load_company_list(path)
