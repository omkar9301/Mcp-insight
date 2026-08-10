import pytest

from app.advisory import _extract_json


def test_extracts_plain_json():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extracts_json_wrapped_in_markdown_fence():
    raw = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert _extract_json(raw) == {"a": 1, "b": [2, 3]}


def test_extracts_json_with_trailing_prose():
    raw = 'Here is the analysis:\n{"a": 1}\nHope that helps!'
    assert _extract_json(raw) == {"a": 1}


def test_handles_curly_braces_inside_string_values():
    # This is exactly the shape that broke naive raw.rindex("}") slicing:
    # a string value containing a brace-like character before the real
    # closing brace, or nested structures with strings mentioning "{}".
    raw = '{"summary": "uses config like {key: value} in practice", "count": 3}'
    result = _extract_json(raw)
    assert result["summary"] == "uses config like {key: value} in practice"
    assert result["count"] == 3


def test_handles_nested_arrays_and_multiple_fields():
    raw = (
        '{"summary": "x", "prevention": ["step one", "step two, with a comma"], '
        '"industry_references": ["Liu et al. 2023"], "confidence": "high"}'
    )
    result = _extract_json(raw)
    assert result["prevention"] == ["step one", "step two, with a comma"]
    assert result["confidence"] == "high"


def test_raises_when_no_json_object_present():
    with pytest.raises(Exception):
        _extract_json("no json here at all")
