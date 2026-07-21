import time

from mcp_insight.capture import PendingRequestTracker, parse_line


def test_parse_line_valid_json():
    msg = parse_line("client_to_server", '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n')
    assert msg.parsed is not None
    assert msg.method == "initialize"
    assert msg.msg_id == 1


def test_parse_line_invalid_json_is_forwarded_but_unparsed():
    msg = parse_line("server_to_client", "not json at all\n")
    assert msg.parsed is None
    assert msg.raw == "not json at all\n"


def test_parse_line_blank_line():
    msg = parse_line("client_to_server", "\n")
    assert msg.parsed is None


def test_is_response_detection():
    req = parse_line("client_to_server", '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{}}\n')
    resp = parse_line("server_to_client", '{"jsonrpc":"2.0","id":1,"result":{}}\n')
    err = parse_line("server_to_client", '{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"x"}}\n')
    notif = parse_line("client_to_server", '{"jsonrpc":"2.0","method":"notifications/initialized"}\n')

    assert not req.is_response
    assert resp.is_response
    assert err.is_response
    assert not notif.is_response


def test_pending_request_tracker_matches_request_to_response():
    tracker = PendingRequestTracker()
    req = parse_line(
        "client_to_server",
        '{"jsonrpc":"2.0","id":42,"method":"tools/call","params":{"name":"add_numbers","arguments":{"a":1,"b":2}}}\n',
    )
    tracker.on_request(req)

    resp = parse_line("server_to_client", '{"jsonrpc":"2.0","id":42,"result":{"sum":3}}\n')
    matched = tracker.on_response(resp)

    assert matched is not None
    assert matched["method"] == "tools/call"
    assert matched["is_error"] is False
    assert matched["result"] == {"sum": 3}
    assert matched["latency_ms"] >= 0


def test_pending_request_tracker_unknown_response_id_returns_none():
    tracker = PendingRequestTracker()
    resp = parse_line("server_to_client", '{"jsonrpc":"2.0","id":999,"result":{}}\n')
    assert tracker.on_response(resp) is None


def test_pending_request_tracker_error_response():
    tracker = PendingRequestTracker()
    tracker.on_request(parse_line("client_to_server", '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{}}\n'))
    resp = parse_line("server_to_client", '{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"boom"}}\n')
    matched = tracker.on_response(resp)
    assert matched["is_error"] is True
    assert matched["error"]["message"] == "boom"
