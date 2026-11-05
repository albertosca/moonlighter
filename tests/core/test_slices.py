from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from moonlighter.core import slices
from moonlighter.core.slices import (
    CAPABILITIES,
    SLICES,
    capabilities,
    installed_slices,
    slice_epilog,
)


def test_installed_slices_always_answers_for_all_four():
    installed = installed_slices()
    assert set(installed) == set(SLICES)
    # This dev environment has every wheel installed.
    assert all(installed.values())


def test_installed_slices_reports_a_missing_wheel_as_false_not_absent():
    def fake_distribution(name):
        if name == "moonlighter-email":
            raise PackageNotFoundError(name)
        return object()

    with patch.object(slices, "distribution", fake_distribution):
        installed = slices.installed_slices()
    assert installed == {"scan": True, "apply": True, "email": False, "full": True}


def test_capabilities_split_by_what_is_installed():
    live, missing = capabilities({"scan": True, "apply": False, "email": False, "full": False})
    assert [capability.name for capability in live] == ["discovery"]
    assert [capability.name for capability in missing] == [
        "sheets",
        "tracking",
        "scan-to-sheet",
        "alias-round-trip",
        "mcp-server",
    ]


def test_every_capability_names_only_known_slices():
    for capability in CAPABILITIES:
        assert capability.needs <= set(SLICES), capability.name


def test_slice_epilog_says_what_is_installed_and_what_each_missing_slice_unlocks():
    text = slice_epilog({"scan": True, "apply": True, "email": False, "full": False})
    assert "installed: scan, apply" in text
    assert "email" in text
    assert "moonlighter-email sync" in text
    assert "tracking" in text
    assert "full" in text
    assert "mcp-server" in text
    # Live capabilities are not advertised as missing.
    assert "would add: discovery" not in text


def test_slice_epilog_tolerates_a_dict_missing_some_slice_keys():
    # A caller can pass a partial dict (e.g. a scan-only install's own view of
    # itself, which never heard of "apply"/"email"/"full") -- slice_epilog
    # must treat an absent key the same as installed=False, matching
    # capabilities()'s own installed.get(slice_name, False), not raise KeyError.
    text = slice_epilog({"scan": True})
    assert text.startswith("installed: scan")


def test_slice_epilog_pins_one_missing_line_verbatim():
    # A human reading --help depends on this exact wording ("install X ->
    # would add: NAME (cmds) -- summary"); scripts read doctor's JSON instead
    # (the jq example in guide/*/reference/cli.md).
    # Membership checks (as in the test above) pass under a renamed field or
    # a reordered/reworded line -- this test fails the moment the format
    # actually changes, which is the point of a pin.
    text = slice_epilog({"scan": True, "apply": False, "email": False, "full": False})
    lines = text.splitlines()
    sheets_lines = [line for line in lines if "would add: sheets" in line]
    assert sheets_lines == [
        (
            "  install apply -> would add: sheets (moonlighter-apply prepare)"
            " -- compose a paste-ready application sheet, from a job id or straight from a URL"
        )
    ]


def test_slice_epilog_pins_the_whole_text_of_a_scan_only_install():
    # Every missing line at once: CAPABILITIES order, the needs not yet
    # installed (sorted, joined), and a command list only when there is one.
    text = slice_epilog({"scan": True, "apply": False, "email": False, "full": False})
    assert text == (
        "installed: scan\n"
        "  install apply -> would add: sheets (moonlighter-apply prepare)"
        " -- compose a paste-ready application sheet, from a job id or straight from a URL\n"
        "  install email -> would add: tracking (moonlighter-email sync, moonlighter-email register)"
        " -- register applications and match Gmail replies back to them\n"
        "  install apply -> would add: scan-to-sheet"
        " -- one script: scan, pick by score, prepare a sheet for each\n"
        "  install apply, email -> would add: alias-round-trip"
        " -- the tracking alias a sheet mints is the one sync matches replies against\n"
        "  install full -> would add: mcp-server (moonlighter)"
        " -- the MCP server for Claude Code, plus answer-bank promotion"
        " when a reply advances an application"
    )
