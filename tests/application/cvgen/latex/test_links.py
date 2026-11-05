import httpx
import pytest

from moonlighter.application.cvgen.latex import links
from moonlighter.application.cvgen.latex.links import check_links, link_report, template_links

HEADER = r"""
\social[linkedin]{albertosca}
\social[github]{albertoalbuquerque}
% \social[twitter]{commented-out}
\homepage{albertosca.dev}
      \githubsocialsymbol~\httplink[albertosca]{github.com/albertosca}%
\social[linkedin]{{{LINKEDIN_USERNAME}}}
"""


def _client(statuses: dict[str, int]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url not in statuses:
            raise httpx.ConnectError("no route", request=request)
        return httpx.Response(statuses[url])

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_template_links_reads_social_and_http_links_and_skips_comments_and_markers():
    assert template_links(HEADER) == [
        "https://www.linkedin.com/in/albertosca",
        "https://github.com/albertoalbuquerque",
        "https://albertosca.dev",
        "https://github.com/albertosca",
    ]


def test_template_links_skips_a_link_commented_out_mid_line():
    text = r"\social[github]{albertosca} % \social[github]{dead-old-account}"
    assert template_links(text) == ["https://github.com/albertosca"]


def test_template_links_reads_a_line_break_before_a_comment_as_a_comment():
    """A LaTeX line break (two backslashes) makes the % after it a comment;
    only an odd number of backslashes escapes it (2026-09-29 re-review).
    """
    assert template_links(r"\\ % \social[github]{dead}") == []
    assert template_links(r"\homepage{a.dev/50\%off}") == ["https://a.dev/50\\%off"]


def test_template_links_lists_a_repeated_link_once():
    text = r"\social[github]{albertosca}" + "\n" + r"\httplink{https://github.com/albertosca}"
    assert template_links(text) == ["https://github.com/albertosca"]


@pytest.mark.asyncio
async def test_check_links_flags_a_404_and_passes_a_200():
    async with _client(
        {"https://github.com/albertosca": 200, "https://github.com/albertoalbuquerque": 404}
    ) as client:
        report = await check_links(
            ["https://github.com/albertosca", "https://github.com/albertoalbuquerque"], client
        )
    assert report == [
        {"url": "https://github.com/albertosca", "status": 200, "ok": True, "note": None},
        {"url": "https://github.com/albertoalbuquerque", "status": 404, "ok": False, "note": None},
    ]


@pytest.mark.asyncio
async def test_check_links_does_not_call_linkedins_bot_wall_broken():
    """LinkedIn answers automated requests with 999: that says nothing about the
    profile, so it is reported as unverified rather than as a broken link.
    """
    async with _client({"https://www.linkedin.com/in/albertosca": 999}) as client:
        report = await check_links(["https://www.linkedin.com/in/albertosca"], client)
    assert report[0]["ok"] is None
    assert "automated" in report[0]["note"]


@pytest.mark.asyncio
async def test_check_links_reports_an_unreachable_host_as_broken():
    async with _client({}) as client:
        report = await check_links(["https://nowhere.example"], client)
    assert report[0]["ok"] is False
    assert report[0]["status"] is None
    assert "no route" in report[0]["note"]


@pytest.mark.asyncio
async def test_link_report_reads_both_templates_from_the_configured_directory(tmp_path):

    (tmp_path / "cv-template.en.tex").write_text(r"\social[github]{albertosca}")
    (tmp_path / "cv-template.pt.tex").write_text(
        r"\social[github]{albertosca}" + "\n" + r"\homepage{albertosca.dev}"
    )
    config = {"cv": {"template_dir": str(tmp_path)}}
    async with _client(
        {"https://github.com/albertosca": 200, "https://albertosca.dev": 200}
    ) as client:
        report = await link_report(config, client)
    assert [entry["url"] for entry in report] == [
        "https://github.com/albertosca",
        "https://albertosca.dev",
    ]


@pytest.mark.asyncio
async def test_link_report_is_empty_without_templates(tmp_path):

    report = await link_report({"cv": {"template_dir": str(tmp_path)}})
    assert report == []


@pytest.mark.asyncio
async def test_link_report_opens_a_client_that_follows_redirects(tmp_path, monkeypatch):
    """A profile URL commonly redirects (http→https, trailing slash): without
    following redirects every such link would read as a 3xx, not as working.
    """
    (tmp_path / "cv-template.en.tex").write_text(r"\social[github]{albertosca}")
    opened: dict = {}
    real_client = httpx.AsyncClient

    def fake_client(**options):
        opened.update(options)
        return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    monkeypatch.setattr(links.httpx, "AsyncClient", fake_client)
    report = await links.link_report({"cv": {"template_dir": str(tmp_path)}})
    assert report[0]["ok"] is True
    assert opened["follow_redirects"] is True
    assert "User-Agent" in opened["headers"]
