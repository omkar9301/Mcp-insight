from mcp_insight.schema_guard import SchemaGuard


INIT_RESULT = {
    "protocolVersion": "2025-06-18",
    "capabilities": {
        "tools": [
            {
                "name": "add_numbers",
                "outputSchema": {
                    "type": "object",
                    "properties": {"sum": {"type": "number"}},
                    "required": ["sum"],
                },
            }
        ]
    },
}


def test_ingest_initialize_response_captures_schema():
    guard = SchemaGuard()
    guard.ingest_initialize_response(INIT_RESULT)
    assert guard.initialized is True
    assert "add_numbers" in guard.tool_schemas


def test_check_tool_result_valid_passes():
    guard = SchemaGuard()
    guard.ingest_initialize_response(INIT_RESULT)
    assert guard.check_tool_result("add_numbers", {"sum": 5}) is None


def test_check_tool_result_missing_required_field_flags_violation():
    guard = SchemaGuard()
    guard.ingest_initialize_response(INIT_RESULT)
    violation = guard.check_tool_result("add_numbers", {"total": 5})
    assert violation is not None
    assert violation["tool"] == "add_numbers"
    assert "required" in violation["violation"]


def test_check_tool_result_unknown_tool_returns_none():
    guard = SchemaGuard()
    guard.ingest_initialize_response(INIT_RESULT)
    assert guard.check_tool_result("unknown_tool", {"anything": 1}) is None


def test_ingest_initialize_response_handles_missing_capabilities():
    guard = SchemaGuard()
    guard.ingest_initialize_response({"protocolVersion": "2025-06-18"})
    assert guard.initialized is True
    assert guard.tool_schemas == {}


def test_ingest_initialize_response_handles_none():
    guard = SchemaGuard()
    guard.ingest_initialize_response(None)
    assert guard.initialized is False
