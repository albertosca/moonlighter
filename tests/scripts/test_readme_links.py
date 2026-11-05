import pytest

import readme_links


def test_slug_follows_github_rules():
    slug = readme_links.slug
    assert slug("Extensions (adding a new ATS scanner)") == "extensions-adding-a-new-ats-scanner"
    assert slug("Instalação") == "instalação"
    assert slug("`moonlighter-scan` doctor") == "moonlighter-scan-doctor"
    assert slug("Sixty seconds of it") == "sixty-seconds-of-it"


def test_a_linked_heading_keeps_its_text_and_loses_its_url():
    assert readme_links.slug("See [the guide](guide/page.md) now") == "see-the-guide-now"


def test_duplicate_headings_get_numbered_slugs():
    assert readme_links.anchors("# Setup\n\n## Setup\n\n## Setup\n") == {
        "setup",
        "setup-1",
        "setup-2",
    }


def test_anchor_ignores_headings_in_code_fences():
    assert readme_links.anchors("## Real\n\n```sh\n# not-a-heading\n```\n") == {"real"}


def test_closing_hashes_and_deep_headings_are_part_of_the_syntax():
    assert readme_links.anchors("###### Deep ######\n####### seven hashes\n") == {"deep"}


def test_link_problems_find_dead_files_and_anchors(tmp_path):
    (tmp_path / "guide").mkdir()
    (tmp_path / "guide/page.md").write_text("## Target\n")
    (tmp_path / "README.md").write_text(
        "[ok](guide/page.md#target) [bad-anchor](guide/page.md#nope) [gone](missing.md) "
        '[self](#local) [web](https://example.com) <img src="assets/x.svg">\n\n## Local\n'
    )
    problems = readme_links.link_problems(tmp_path, "README.md")
    assert sorted(problems) == [
        "README.md: assets/x.svg does not exist",
        "README.md: guide/page.md#nope — no such anchor",
        "README.md: missing.md does not exist",
    ]


def test_problems_come_in_the_order_markdown_links_then_html_references(tmp_path):
    (tmp_path / "README.md").write_text('<img src="b.svg"> [a](a.md)\n')

    assert readme_links.link_problems(tmp_path, "README.md") == [
        "README.md: a.md does not exist",
        "README.md: b.svg does not exist",
    ]


def test_an_anchor_into_a_file_that_is_not_markdown_is_not_checked(tmp_path):
    (tmp_path / "data.txt").write_text("no headings\n")
    (tmp_path / "README.md").write_text("[x](data.txt#anything)\n")

    assert readme_links.link_problems(tmp_path, "README.md") == []


def test_a_self_link_to_a_missing_anchor_is_reported(tmp_path):
    (tmp_path / "README.md").write_text("[self](#nowhere)\n\n## Elsewhere\n")

    assert readme_links.link_problems(tmp_path, "README.md") == [
        "README.md: #nowhere — no such anchor"
    ]


@pytest.mark.parametrize("target", ["https://x.test/a", "mailto:a@x.test", "tel:123"])
def test_absolute_targets_are_never_checked(tmp_path, target):
    (tmp_path / "README.md").write_text(f"[x]({target})\n")

    assert readme_links.link_problems(tmp_path, "README.md") == []
