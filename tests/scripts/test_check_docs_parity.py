import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _cdp():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import check_docs_parity

    return check_docs_parity


def _page(root: Path, lang: str, rel: str, text: str) -> None:
    path = root / lang / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_matching_trees_have_no_problems(tmp_path):
    _page(tmp_path, "en", "index.md", "# A\n\n## One\n\n### Sub\n")
    _page(tmp_path, "pt", "index.md", "# A\n\n## Um\n\n### Sub\n")
    assert _cdp().parity_problems(tmp_path) == []


def test_a_page_missing_in_one_language_is_reported_both_ways(tmp_path):
    _page(tmp_path, "en", "index.md", "# A\n")
    _page(tmp_path, "en", "guides/cv.md", "# CV\n")
    _page(tmp_path, "pt", "index.md", "# A\n")
    _page(tmp_path, "pt", "faq.md", "# FAQ\n")
    problems = _cdp().parity_problems(tmp_path)
    assert "missing in pt: guides/cv.md" in problems
    assert "missing in en: faq.md" in problems


def test_a_different_heading_sequence_is_reported(tmp_path):
    _page(tmp_path, "en", "index.md", "## One\n\n## Two\n")
    _page(tmp_path, "pt", "index.md", "## Um\n\n### Dois\n")
    [problem] = _cdp().parity_problems(tmp_path)
    assert "index.md" in problem and "[2, 2]" in problem and "[2, 3]" in problem


def test_headings_inside_code_fences_are_ignored(tmp_path):
    _page(tmp_path, "en", "index.md", "## Run\n\n```bash\n## not a heading\n```\n")
    _page(tmp_path, "pt", "index.md", "## Rodar\n\n```bash\n# comentário\n```\n")
    assert _cdp().parity_problems(tmp_path) == []


def test_an_empty_english_tree_is_a_problem_not_a_pass(tmp_path):
    (tmp_path / "en").mkdir()
    (tmp_path / "pt").mkdir()
    assert _cdp().parity_problems(tmp_path) == [f"no pages under {tmp_path / 'en'}"]


def test_main_exit_codes(tmp_path, capsys):
    _page(tmp_path, "en", "index.md", "## One\n")
    _page(tmp_path, "pt", "index.md", "## Um\n")
    assert _cdp().main(["x", str(tmp_path)]) == 0
    _page(tmp_path, "en", "extra.md", "# X\n")
    assert _cdp().main(["x", str(tmp_path)]) == 1
    assert "missing in pt: extra.md" in capsys.readouterr().err
