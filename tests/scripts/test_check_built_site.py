from pathlib import Path

import check_built_site

DATE = '<span class="md-source-file__fact">2026-01-15</span>'
BASE = "https://albertosca.github.io/moonlighter/"


def _alternates(page_path: str) -> str:
    return (
        f'<link rel="alternate" href="{BASE}{page_path}" hreflang="en">'
        f'<link rel="alternate" href="{BASE}pt/{page_path}" hreflang="pt">'
        f'<link rel="alternate" href="{BASE}{page_path}" hreflang="x-default">'
    )


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _good_site(root: Path) -> tuple[Path, Path]:
    site, guide = root / "site", root / "guide"
    for language_root in (site, site / "pt"):
        _write(language_root / "stylesheets/night-shift.css", ":root{}")
        _write(language_root / "index.html", DATE + _alternates(""))
        _write(language_root / "guides/cv/index.html", DATE + _alternates("guides/cv/"))
        _write(language_root / "sitemap.xml", "<urlset/>")
        _write(language_root / "guides/cv/sitemap.xml", "<urlset/>")
    _write(site / "llms.txt", "# moonlighter")
    _write(site / "assets/diagrams/how-light.svg", "<svg/>")
    for language in ("en", "pt"):
        _write(
            guide / language / "index.md",
            "![how](https://albertosca.github.io/moonlighter/assets/diagrams/how-light.svg)",
        )
        _write(guide / language / "guides/cv.md", "# CV")
    _write(guide / "en/llms.txt", "https://albertosca.github.io/moonlighter/pt/")
    return site, guide


def test_page_output_maps_index_and_pages():
    assert check_built_site.page_output(Path("index.md")) == Path("index.html")
    assert check_built_site.page_output(Path("guides/cv.md")) == Path("guides/cv/index.html")
    assert check_built_site.page_output(Path("guides/index.md")) == Path("guides/index.html")


def test_a_good_site_has_no_problems(tmp_path):
    site, guide = _good_site(tmp_path)
    assert check_built_site.site_problems(site, guide, require_dates=True) == []


def test_missing_stylesheet_in_one_language_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "pt/stylesheets/night-shift.css").unlink()
    assert check_built_site.site_problems(site, guide, require_dates=False) == [
        f"missing {site / 'pt/stylesheets/night-shift.css'}"
    ]


def test_missing_llms_txt_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "llms.txt").unlink()
    assert check_built_site.site_problems(site, guide, require_dates=False) == [
        "missing llms.txt at the site root"
    ]


def test_a_pages_url_with_no_built_file_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "assets/diagrams/how-light.svg").unlink()
    problems = check_built_site.site_problems(site, guide, require_dates=False)
    assert len(problems) == 2
    assert all("how-light.svg" in problem for problem in problems)


def test_a_page_without_a_revision_date_fails_only_when_required(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "pt/guides/cv/index.html").write_text("<p>no date</p>" + _alternates("guides/cv/"))
    assert check_built_site.site_problems(site, guide, require_dates=False) == []
    [problem] = check_built_site.site_problems(site, guide, require_dates=True)
    assert "pt/guides/cv/index.html" in problem


def test_a_markdown_page_with_no_html_output_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "guides/cv/index.html").unlink()
    [problem] = check_built_site.site_problems(site, guide, require_dates=True)
    assert "guides/cv/index.html" in problem


def test_main_exit_codes(tmp_path, capsys):
    site, guide = _good_site(tmp_path)
    assert check_built_site.main(["x", str(site), str(guide), "--require-dates"]) == 0
    (site / "llms.txt").unlink()
    assert check_built_site.main(["x", str(site), str(guide)]) == 1
    assert "llms.txt" in capsys.readouterr().err


def test_a_readme_pages_url_missing_from_the_site_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    _write(tmp_path / "README.md", "[FAQ](https://albertosca.github.io/moonlighter/faq/)")
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert (
        problem
        == f"{tmp_path / 'README.md'}: https://albertosca.github.io/moonlighter/faq/ is not in the built site"
    )


def test_package_readmes_are_scanned_too(tmp_path):
    site, guide = _good_site(tmp_path)
    _write(
        tmp_path / "packages/scan/README.pt.md", "https://albertosca.github.io/moonlighter/pt/faq/"
    )
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert "packages/scan/README.pt.md" in problem
    assert "pt/faq/" in problem


def test_a_readme_anchor_missing_from_the_target_page_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    (site / "guides/cv/index.html").write_text(
        DATE + _alternates("guides/cv/") + '<h2 id="kept">Kept</h2>'
    )
    _write(
        tmp_path / "README.md",
        "[a](https://albertosca.github.io/moonlighter/guides/cv/#kept) "
        "[b](https://albertosca.github.io/moonlighter/guides/cv/#renamed)",
    )
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert problem == (
        f"{tmp_path / 'README.md'}: https://albertosca.github.io/moonlighter/guides/cv/#renamed "
        f'has no id="renamed" in {site / "guides/cv/index.html"}'
    )


def test_a_bare_url_ending_a_sentence_keeps_its_punctuation_out(tmp_path):
    site, guide = _good_site(tmp_path)
    _write(
        guide / "en/llms.txt",
        "See https://albertosca.github.io/moonlighter/guides/cv/. Or "
        "https://albertosca.github.io/moonlighter/pt/, https://albertosca.github.io/moonlighter/llms.txt!",
    )
    assert check_built_site.site_problems(site, guide, require_dates=False) == []


def test_hreflang_pointing_at_the_language_home_is_reported(tmp_path):
    # The theme's own links: every page named the other language's HOME, as a
    # relative URL -- Google requires absolute hreflang URLs and drops these.
    site, guide = _good_site(tmp_path)
    theme_links = (
        '<link rel="alternate" href="/moonlighter/" hreflang="en">'
        '<link rel="alternate" href="/moonlighter/pt/" hreflang="pt">'
    )
    _write(site / "pt/guides/cv/index.html", DATE + theme_links)
    problems = check_built_site.site_problems(site, guide, require_dates=False)
    assert len(problems) == 1
    assert "hreflang" in problems[0]
    assert "pt/guides/cv/index.html" in problems[0]


def test_a_missing_hreflang_language_is_reported(tmp_path):
    site, guide = _good_site(tmp_path)
    only_en = f'<link rel="alternate" href="{BASE}guides/cv/" hreflang="en">'
    _write(site / "guides/cv/index.html", DATE + only_en)
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert "hreflang" in problem


def test_theme_links_left_beside_the_right_ones_are_reported(tmp_path):
    # If the override stops stripping the theme's links, the page carries both
    # sets; the last-wins reading would see only the right ones and pass.
    site, guide = _good_site(tmp_path)
    theme_links = '<link rel="alternate" href="/moonlighter/pt/" hreflang="pt">'
    _write(site / "guides/cv/index.html", DATE + theme_links + _alternates("guides/cv/"))
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert "hreflang" in problem


def test_a_page_directory_without_its_sitemap_copy_is_reported(tmp_path):
    # The theme's language switcher fetches sitemap.xml beside every hreflang
    # URL; with per-page hreflang, a page directory without a copy is a 404.
    site, guide = _good_site(tmp_path)
    (site / "pt/guides/cv/sitemap.xml").unlink()
    [problem] = check_built_site.site_problems(site, guide, require_dates=False)
    assert "sitemap.xml" in problem
    assert "pt/guides/cv" in problem
