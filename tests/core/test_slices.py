from importlib.metadata import PackageNotFoundError
from unittest.mock import patch


def test_installed_slices_always_answers_for_all_four():
    from moonlighter.core.slices import SLICES, installed_slices

    installed = installed_slices()
    assert set(installed) == set(SLICES)
    # This dev environment has every wheel installed.
    assert all(installed.values())


def test_installed_slices_reports_a_missing_wheel_as_false_not_absent():
    from moonlighter.core import slices

    def fake_distribution(name):
        if name == "moonlighter-email":
            raise PackageNotFoundError(name)
        return object()

    with patch.object(slices, "distribution", fake_distribution):
        installed = slices.installed_slices()
    assert installed == {"scan": True, "apply": True, "email": False, "full": True}


def test_capabilities_split_by_what_is_installed():
    from moonlighter.core.slices import capabilities

    live, missing = capabilities({"scan": True, "apply": False, "email": False, "full": False})
    assert [c.name for c in live] == ["discovery"]
    assert [c.name for c in missing] == [
        "sheets",
        "tracking",
        "scan-to-sheet",
        "alias-round-trip",
        "mcp-server",
    ]


def test_every_capability_names_only_known_slices():
    from moonlighter.core.slices import CAPABILITIES, SLICES

    for c in CAPABILITIES:
        assert c.needs <= set(SLICES), c.name


def test_slice_epilog_says_what_is_installed_and_what_each_missing_slice_unlocks():
    from moonlighter.core.slices import slice_epilog

    text = slice_epilog({"scan": True, "apply": True, "email": False, "full": False})
    assert "installed: scan, apply" in text
    assert "email" in text and "moonlighter-email sync" in text and "tracking" in text
    assert "full" in text and "mcp-server" in text
    # Live capabilities are not advertised as missing.
    assert "would add: discovery" not in text


def test_slice_epilog_tolerates_a_dict_missing_some_slice_keys():
    # A caller can pass a partial dict (e.g. a scan-only install's own view of
    # itself, which never heard of "apply"/"email"/"full") -- slice_epilog
    # must treat an absent key the same as installed=False, matching
    # capabilities()'s own installed.get(s, False), not raise KeyError.
    from moonlighter.core.slices import slice_epilog

    text = slice_epilog({"scan": True})
    assert text.startswith("installed: scan")


def test_slice_epilog_pins_one_missing_line_verbatim():
    # The README's jq example and a human reading --help both depend on this
    # exact wording ("install X -> would add: NAME (cmds) -- summary").
    # Membership checks (as in the test above) pass under a renamed field or
    # a reordered/reworded line -- this test fails the moment the format
    # actually changes, which is the point of a pin.
    from moonlighter.core.slices import slice_epilog

    text = slice_epilog({"scan": True, "apply": False, "email": False, "full": False})
    lines = text.splitlines()
    sheets_lines = [line for line in lines if "would add: sheets" in line]
    assert sheets_lines == [
        "  install apply -> would add: sheets (moonlighter-apply prepare)"
        " -- compose a paste-ready application sheet, from a job id or straight from a URL"
    ]
