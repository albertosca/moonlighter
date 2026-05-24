import json
from candidatador.parsing import _extract_json


def test_extract_json_plain_json_passthrough():
    payload = json.dumps({"score": 7.0, "notes": "ok"})
    assert _extract_json(payload) == payload


def test_extract_json_strips_json_fence():
    payload = {"score": 8.5}
    raw = f"```json\n{json.dumps(payload)}\n```"
    result = _extract_json(raw)
    assert json.loads(result) == payload


def test_extract_json_strips_plain_fence_no_label():
    payload = {"answer": "yes"}
    raw = f"```\n{json.dumps(payload)}\n```"
    result = _extract_json(raw)
    assert json.loads(result) == payload


def test_extract_json_strips_leading_prose():
    payload = {"score": 6.0}
    raw = f"Sure, here is the JSON:\n\n{json.dumps(payload)}"
    result = _extract_json(raw)
    assert json.loads(result) == payload


def test_extract_json_strips_trailing_prose():
    payload = {"score": 9.0}
    raw = f"{json.dumps(payload)}\n\nHope that helps!"
    result = _extract_json(raw)
    assert json.loads(result) == payload


def test_extract_json_whitespace_stripped():
    payload = json.dumps({"x": 1})
    assert _extract_json(f"  {payload}  ") == payload


def test_extract_json_non_json_returns_raw():
    raw = "just plain text with no json"
    assert _extract_json(raw) == raw


def test_extract_json_empty_string_returns_empty():
    assert _extract_json("") == ""


def test_extract_json_fence_with_whitespace_variations():
    payload = {"k": "v"}
    raw = f"```json\n\n{json.dumps(payload)}\n\n```"
    result = _extract_json(raw)
    assert json.loads(result) == payload


def test_extract_json_nested_object_extracted():
    payload = {"outer": {"inner": [1, 2, 3]}}
    raw = f"Result: {json.dumps(payload)} end"
    result = _extract_json(raw)
    assert json.loads(result) == payload
