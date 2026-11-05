"""normalize_feed_description turns a feed's HTML description into tidy plain text, or None when no text is left."""

from moonlighter.core.posting import normalize_feed_description


def test_tags_only_description_yields_none():
    assert normalize_feed_description("<p> </p><br/>") is None
    assert normalize_feed_description("") is None


def test_nested_tags_are_stripped_whitespace_collapsed_and_punctuation_reattached():
    raw = "<p>Build <b>great</b> <i>things</i> .</p>\n<ul><li>Remote , worldwide</li></ul>"
    assert normalize_feed_description(raw) == "Build great things. Remote, worldwide"
