"""Pins the exact problem lines, their order and the exit codes of check_built_site."""

import check_built_site

from tests.scripts.test_check_built_site import BASE, DATE, _alternates, _good_site, _write


def test_main_prints_the_ok_line_and_nothing_on_stderr(tmp_path, capsys):
    site, guide = _good_site(tmp_path)

    assert check_built_site.main(["x", str(site), str(guide)]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Built site OK.\n"
    assert captured.err == ""


def test_the_require_dates_flag_is_only_read_after_the_two_paths(tmp_path, capsys):
    site, guide = _good_site(tmp_path)
    (site / "guides/cv/index.html").write_text("<p>no date</p>" + _alternates("guides/cv/"))

    assert check_built_site.main(["x", str(site), str(guide), "--require-dates"]) == 1
    assert (
        capsys.readouterr().err == f"{site / 'guides/cv/index.html'}: no revision date rendered\n"
    )
    assert check_built_site.main(["x", str(site), str(guide)]) == 0
    assert check_built_site.main(["--require-dates", str(site), str(guide)]) == 0


def test_main_prints_every_problem_on_stderr_in_the_order_site_problems_finds_them(
    tmp_path, capsys
):
    site, guide = _good_site(tmp_path)
    (site / "pt/stylesheets/night-shift.css").unlink()
    (site / "llms.txt").unlink()
    _write(guide / "en/guides/cv.md", f"# CV\n{BASE}missing/ and {BASE}#nowhere")
    (site / "pt/guides/cv/index.html").unlink()
    _write(site / "guides/cv/index.html", "<p>no date</p>")
    (site / "guides/cv/sitemap.xml").unlink()

    exit_code = check_built_site.main(["x", str(site), str(guide), "--require-dates"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    expected_alternates = sorted(check_built_site.expected_alternates("guides/cv/").items())
    hreflang_problem = (
        f"{site / 'guides/cv/index.html'}: hreflang links [] != {expected_alternates}"
    )
    assert captured.err.splitlines() == [
        f"missing {site / 'pt/stylesheets/night-shift.css'}",
        "missing llms.txt at the site root",
        f"{guide / 'en/guides/cv.md'}: {BASE}missing/ is not in the built site",
        f'{guide / "en/guides/cv.md"}: {BASE}#nowhere has no id="nowhere" in {site / "index.html"}',
        f"{site / 'guides/cv/index.html'}: no revision date rendered",
        f"{site / 'guides/cv'}: no sitemap.xml copy for the language switcher",
        hreflang_problem,
        f"{guide / 'pt/guides/cv.md'}: no built page at {site / 'pt/guides/cv/index.html'}",
    ]


def test_the_sources_scanned_for_pages_urls_are_guide_markdown_guide_text_and_readmes(
    tmp_path, capsys
):
    site, guide = _good_site(tmp_path)
    (tmp_path / "README.md").write_text(f"{BASE}one.html")
    _write(tmp_path / "packages/core/README.pt.md", f"{BASE}two.html")
    _write(guide / "pt/notes.txt", f"{BASE}three.html.")
    _write(guide / "pt/ignored.rst", f"{BASE}four.html")

    assert check_built_site.main(["x", str(site), str(guide)]) == 1

    assert capsys.readouterr().err.splitlines() == [
        f"{guide / 'pt/notes.txt'}: {BASE}three.html is not in the built site",
        f"{tmp_path / 'README.md'}: {BASE}one.html is not in the built site",
        f"{tmp_path / 'packages/core/README.pt.md'}: {BASE}two.html is not in the built site",
    ]


def test_a_directory_url_without_a_trailing_slash_resolves_to_its_index(tmp_path):
    site, guide = _good_site(tmp_path)
    _write(guide / "en/guides/cv.md", f"{BASE}guides/cv and {BASE}pt/guides/cv/#top")
    _write(site / "guides/cv/index.html", DATE + _alternates("guides/cv/") + '<a id="top">')

    assert check_built_site.site_problems(site, guide, require_dates=True) == [
        f'{guide / "en/guides/cv.md"}: {BASE}pt/guides/cv/#top has no id="top" in {site / "pt/guides/cv/index.html"}'
    ]
