from mcp_insight.capture import parse_line
from mcp_insight.interceptor import Interceptor


def _feed(interceptor, direction, raw_dict):
    import json

    interceptor.handle_message(parse_line(direction, json.dumps(raw_dict) + "\n"))


INIT_RESULT_WITH_TOOLS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {
        "tools": [
            {
                "name": "add_numbers",
                "description": "Adds two numbers",
                "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}}},
                "outputSchema": {"type": "object", "properties": {"sum": {"type": "number"}}, "required": ["sum"]},
            }
        ]
    },
}


def test_capabilities_event_sent_on_initialize_with_inline_tools():
    interceptor = Interceptor(server_id="s1", ingestion_url="http://unreachable.invalid", api_key="")
    _feed(interceptor, "client_to_server", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    _feed(interceptor, "server_to_client", {"jsonrpc": "2.0", "id": 1, "result": INIT_RESULT_WITH_TOOLS})

    events = list(interceptor.buffer._queue)
    capability_events = [e for e in events if e["type"] == "server_capabilities"]
    assert len(capability_events) == 1
    assert capability_events[0]["tools"][0]["name"] == "add_numbers"
    assert capability_events[0]["tools"][0]["output_schema"]["required"] == ["sum"]


def test_capabilities_event_not_resent_when_unchanged():
    interceptor = Interceptor(server_id="s1", ingestion_url="http://unreachable.invalid", api_key="")
    _feed(interceptor, "client_to_server", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    _feed(interceptor, "server_to_client", {"jsonrpc": "2.0", "id": 1, "result": INIT_RESULT_WITH_TOOLS})

    # A completely unrelated tools/call round-trip afterwards must not
    # re-trigger a capabilities event since the registry didn't change.
    _feed(interceptor, "client_to_server", {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "add_numbers", "arguments": {"a": 1, "b": 2}},
    })
    _feed(interceptor, "server_to_client", {"jsonrpc": "2.0", "id": 2, "result": {"sum": 3}})

    events = list(interceptor.buffer._queue)
    capability_events = [e for e in events if e["type"] == "server_capabilities"]
    assert len(capability_events) == 1


def test_capabilities_captured_from_tools_list_call():
    interceptor = Interceptor(server_id="s1", ingestion_url="http://unreachable.invalid", api_key="")
    # initialize with no inline tools
    _feed(interceptor, "client_to_server", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    _feed(interceptor, "server_to_client", {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})

    _feed(interceptor, "client_to_server", {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    _feed(interceptor, "server_to_client", {
        "jsonrpc": "2.0", "id": 2,
        "result": {"tools": [{"name": "search", "description": "Searches things"}]},
    })

    events = list(interceptor.buffer._queue)
    capability_events = [e for e in events if e["type"] == "server_capabilities"]
    assert len(capability_events) == 1
    assert capability_events[0]["tools"][0]["name"] == "search"
