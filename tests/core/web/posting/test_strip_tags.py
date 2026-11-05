"""strip_tags is public for other packages, and turns markup into whitespace-collapsed text, or None when no text is left."""

from moonlighter.core.web.posting import strip_tags


def test_strip_tags_is_public_so_other_packages_can_import_it_directly():
    # discovery/sources/company_boards/inhire.py imports this across a package boundary; a
    # leading underscore would make that a private-symbol reach-in.
    assert strip_tags("<p>Hello  world</p>") == "Hello world"
    assert strip_tags("  ") is None
