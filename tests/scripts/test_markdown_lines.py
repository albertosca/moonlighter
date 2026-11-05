import markdown_lines


def _lines(text: str) -> list[str]:
    return list(markdown_lines.lines_outside_fences(text))


def test_lines_outside_a_fence_pass_through_in_order():
    assert _lines("one\ntwo\n") == ["one", "two"]


def test_fence_lines_and_everything_between_them_are_left_out():
    assert _lines("before\n```sh\n# hidden\n```\nafter\n") == ["before", "after"]


def test_a_tilde_fence_hides_its_contents_too():
    assert _lines("a\n~~~\nhidden\n~~~\nb\n") == ["a", "b"]


def test_an_indented_fence_still_counts():
    assert _lines("a\n   ```\nhidden\n   ```\nb\n") == ["a", "b"]


def test_an_unclosed_fence_runs_to_the_end_of_the_text():
    assert _lines("a\n```\nhidden\nstill hidden\n") == ["a"]


def test_a_fence_closed_by_the_other_marker_still_closes():
    assert _lines("a\n```\nhidden\n~~~\nb\n") == ["a", "b"]


def test_empty_text_has_no_lines():
    assert _lines("") == []
