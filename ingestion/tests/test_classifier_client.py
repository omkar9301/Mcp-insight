import pytest

from app.classifier_client import classify_event, describe_fault


def test_describe_fault_silent_failure():
    event = {
        "silent_failure": True,
        "method": "tools/call",
        "schema_violation": {"tool": "add_numbers", "violation": "'sum' is a required property"},
    }
    text = describe_fault(event)
    assert "add_numbers" in text
    assert "required property" in text


def test_describe_fault_error():
    event = {"is_error": True, "method": "tools/call", "error": {"code": -32000, "message": "boom"}}
    text = describe_fault(event)
    assert "tools/call" in text
    assert "boom" in text


def test_describe_fault_protocol_violation():
    event = {"type": "protocol_violation", "subtype": "non_json_on_stdout"}
    text = describe_fault(event)
    assert "non_json_on_stdout" in text


def test_describe_fault_returns_none_for_non_fault_event():
    event = {"type": "rpc_call", "method": "tools/list", "is_error": False}
    assert describe_fault(event) is None


@pytest.mark.asyncio
async def test_classify_event_returns_none_when_classifier_unreachable(monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "classifier_url", "http://127.0.0.1:1")
    event = {"is_error": True, "method": "tools/call", "error": {"code": -1, "message": "x"}}
    result = await classify_event(event)
    assert result is None
