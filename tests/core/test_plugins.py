from moonlighter.core.plugins import discover_entry_points, discover_entry_points_by_name


def test_discover_entry_points_returns_empty_list_for_unknown_group():
    assert discover_entry_points("moonlighter.this_group_does_not_exist") == []


def test_discover_entry_points_loads_a_real_registered_entry_point():
    # moonlighter-core itself doesn't register anything in this group; this proves
    # the loader can resolve an arbitrary importable class by dotted path via a
    # real EntryPoint object, without needing an actual separate installed package.
    from importlib.metadata import EntryPoint
    from unittest.mock import patch

    fake_ep = EntryPoint(
        name="fake",
        value="moonlighter.core.plugins:discover_entry_points",
        group="moonlighter.test_group",
    )
    with patch("moonlighter.core.plugins.entry_points", return_value=[fake_ep]):
        loaded = discover_entry_points("moonlighter.test_group")
    assert loaded == [discover_entry_points]


def test_discover_entry_points_by_name_returns_empty_dict_for_unknown_group():
    assert discover_entry_points_by_name("moonlighter.this_group_does_not_exist") == {}


def test_discover_entry_points_by_name_keys_by_entry_point_name():
    from importlib.metadata import EntryPoint
    from unittest.mock import patch

    fake_ep = EntryPoint(
        name="fake",
        value="moonlighter.core.plugins:discover_entry_points",
        group="moonlighter.test_group",
    )
    with patch("moonlighter.core.plugins.entry_points", return_value=[fake_ep]):
        loaded = discover_entry_points_by_name("moonlighter.test_group")
    assert loaded == {"fake": discover_entry_points}
