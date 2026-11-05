"""Tests for parsing the model reply to a batched evaluation."""

import json

from moonlighter.discovery.evaluation.result_parsing import parse_batch


def test_parse_batch_valid_array_maps_by_order():
    raw = '[{"score": 8.0, "score_notes": "a", "caveats": []}, {"score": 3.0, "score_notes": "b", "caveats": ["x"]}]'
    results = parse_batch(raw, 2)
    assert results is not None
    assert [result.score for result in results] == [8.0, 3.0]
    assert results[1].caveats == ["x"]


def test_parse_batch_wrong_length_returns_none():
    assert parse_batch('[{"score": 8.0}]', 2) is None


def test_parse_batch_more_items_than_requested_returns_none():
    """LLM returns MORE items than n (e.g. hallucinated extras) — also structurally invalid."""
    raw = '[{"score": 1.0}, {"score": 2.0}, {"score": 3.0}]'
    assert parse_batch(raw, 2) is None


def test_parse_batch_non_array_returns_none():
    assert parse_batch('{"score": 8.0}', 1) is None


def test_parse_batch_bare_scalar_top_level_returns_none():
    assert parse_batch("42", 1) is None


def test_parse_batch_invalid_json_returns_none():
    assert parse_batch("not json", 2) is None


def test_parse_batch_empty_string_returns_none():
    assert parse_batch("", 1) is None


def test_parse_batch_empty_array_matches_zero_n():
    assert parse_batch("[]", 0) == []


def test_parse_batch_item_with_missing_keys_uses_defaults():
    results = parse_batch('[{"foo": 1}]', 1)
    assert results is not None
    assert results[0].score == 0.0
    assert results[0].caveats == []


def test_parse_batch_item_wrong_type_string_tolerated_as_default():
    """A non-dict item (LLM returned a bare string/number instead of an
    object) is coerced to {} by parse_batch and gets default field values —
    the malformed item is tolerated, never crashes the batch."""
    results = parse_batch('["oops", 5, null]', 3)
    assert results is not None
    assert all(result.score == 0.0 and result.caveats == [] for result in results)


def test_parse_batch_item_is_nested_list_tolerated_as_default():
    results = parse_batch("[[1, 2, 3]]", 1)
    assert results is not None
    assert results[0].score == 0.0


def test_parse_batch_extracts_json_from_markdown_fence_with_prose():
    """Fallback path: raw isn't valid JSON on its own (has surrounding
    prose + fence) — parse_llm_json must extract it before json.loads."""
    raw = 'Here are the results:\n```json\n[{"score": 6.5, "score_notes": "ok"}]\n```'
    results = parse_batch(raw, 1)
    assert results is not None
    assert results[0].score == 6.5


def test_parse_batch_item_with_malformed_salary_fields_sanitized():
    """A dict item with hostile/wrong-typed salary sub-fields still parses —
    _result_from's per-field coercion sanitizes them instead of raising."""
    raw = json.dumps(
        [
            {
                "score": "not a number",
                "salary_min": -500,
                "salary_max": True,
                "salary_currency": 123,
                "salary_source": "made_up",
            }
        ]
    )
    results = parse_batch(raw, 1)
    assert results is not None
    result = results[0]
    assert result.score == 0.0
    assert result.salary_min is None
    assert result.salary_max is None
    assert result.salary_currency is None
    assert result.salary_source is None
