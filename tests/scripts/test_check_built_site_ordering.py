"""Pins the order check_built_site reports in: the hreflang pairs and the pages it walks."""

from pathlib import Path

import check_built_site

from tests.scripts.test_check_built_site import _good_site, _write


def test_page_alternates_come_sorted_and_keep_a_duplicated_language():
    html = (
        '<link rel="alternate" href="b" hreflang="pt">'
        '<link rel="alternate" href="a" hreflang="pt">'
        '<link rel="alternate" href="a" hreflang="pt">'
        '<link rel="alternate" href="c" hreflang="en">'
        '<link rel="alternate" href="no-language">'
    )

    assert check_built_site.page_alternates(html) == [
        ("en", "c"),
        ("pt", "a"),
        ("pt", "a"),
        ("pt", "b"),
    ]


def test_pages_are_checked_in_sorted_order_whatever_the_filesystem_returns(tmp_path, monkeypatch):
    site, guide = _good_site(tmp_path)
    for name in ("a", "b", "c"):
        _write(guide / "en" / f"{name}.md", "# page")
    real_rglob = Path.rglob
    monkeypatch.setattr(
        Path,
        "rglob",
        lambda self, pattern: iter(sorted(real_rglob(self, pattern), reverse=True)),
    )

    problems = check_built_site.site_problems(site, guide, require_dates=False)

    missing = [problem for problem in problems if "no built page" in problem]
    assert [Path(problem.split(":")[0]).name for problem in missing] == ["a.md", "b.md", "c.md"]
