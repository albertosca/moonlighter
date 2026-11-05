"""prepare_application and prepare_application_from_paste hand off to the assisted service, and their descriptions say what they accept."""

from moonlighter.application.assisted import service as assisted_service
from moonlighter.application.assisted.results import SheetKind, SheetResult
from moonlighter.application.assisted.sources.registry import SOURCES
from moonlighter.mcp_tools.applications import prepare_application, prepare_application_from_paste

from tests._context import make_test_context


async def test_prepare_application_tool_delegates_to_assisted_service(monkeypatch):
    called = {}

    async def fake_prepare(job_id, config, profile):
        called["args"] = (job_id, config, profile)
        return SheetResult(
            kind=SheetKind.JOB_NOT_FOUND,
            composed=[],
            job_title="",
            company="",
            apply_url="",
            error="sheet",
        )

    monkeypatch.setattr(assisted_service, "prepare_application", fake_prepare)
    result = await prepare_application(42, context=make_test_context())
    assert result == "sheet"
    assert called["args"][0] == 42


async def test_prepare_application_from_paste_tool_delegates_to_assisted_service(monkeypatch):
    called = {}

    async def fake_prepare_from_paste(job_id, page_text, config, profile):  # noqa: PLR0917 - stands in for the assisted service, the code under test calls positionally
        called["args"] = (job_id, page_text)
        return SheetResult(
            kind=SheetKind.JOB_NOT_FOUND,
            composed=[],
            job_title="",
            company="",
            apply_url="",
            error="sheet from paste",
        )

    monkeypatch.setattr(assisted_service, "prepare_application_from_paste", fake_prepare_from_paste)
    result = await prepare_application_from_paste(
        42, "copied page text", context=make_test_context()
    )
    assert result == "sheet from paste"
    assert called["args"] == (42, "copied page text")


def test_prepare_application_docstring_names_every_ats_source():
    # The calling model reads this docstring to decide whether to ask for a paste.

    display_names = {
        "greenhouse": "Greenhouse",
        "recruitee": "Recruitee",
        "workable": "Workable",
        "lever": "Lever",
        "inhire": "InHire",
    }
    assert {source.name for source in SOURCES} == set(display_names)
    docstring = " ".join((prepare_application.__doc__ or "").split())
    for display_name in display_names.values():
        assert display_name in docstring
    assert "InHire lists its required fields" in docstring


def test_prepare_application_from_paste_docstring_says_a_published_form_wins():
    docstring = " ".join((prepare_application_from_paste.__doc__ or "").split())
    assert "the paste is ignored" in docstring
