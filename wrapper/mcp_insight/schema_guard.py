"""
mcp_insight.schema_guard

Captures tool/prompt/resource schemas from the MCP `initialize` response,
then validates every subsequent tool result against its own declared
output schema. This is what catches "silent failures": JSON-RPC success
responses whose content quietly violates the server's own contract.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:  # keep the wrapper usable even if the dep is missing
    _HAS_JSONSCHEMA = False


class SchemaGuard:
    def __init__(self) -> None:
        self.tool_schemas: dict[str, dict] = {}
        # Full declared metadata per tool -- name, description, and both
        # schemas -- kept separately from `tool_schemas` (output-schema-only,
        # used on the hot path for validation) so the richer registry used
        # for reporting "what does this server expose" doesn't add lookup
        # cost to every tool result check.
        self.tools: dict[str, dict] = {}
        self.initialized = False

    def ingest_initialize_response(self, result: Optional[dict]) -> None:
        """Called once per session with the parsed `result` field of the
        response to an `initialize` request."""
        if not result:
            return
        capabilities = result.get("capabilities", {})
        tools = capabilities.get("tools")
        # Some servers report tools via a later tools/list call instead of
        # inline in initialize -- handle both by exposing ingest_tools_list.
        if isinstance(tools, list):
            self.ingest_tools_list(tools)
        self.initialized = True

    def ingest_tools_list(self, tools: list[dict]) -> None:
        for tool in tools:
            name = tool.get("name")
            if not name:
                continue
            input_schema = tool.get("inputSchema") or tool.get("input_schema")
            output_schema = tool.get("outputSchema") or tool.get("output_schema")
            if output_schema:
                self.tool_schemas[name] = output_schema
            self.tools[name] = {
                "name": name,
                "description": tool.get("description"),
                "input_schema": input_schema,
                "output_schema": output_schema,
            }

    def check_tool_result(self, tool_name: str, result: Any) -> Optional[dict]:
        """Returns a violation dict if the result breaks its declared
        schema, else None. Returns None (not a violation) for tools with
        no captured schema -- we can't validate what we never saw."""
        schema = self.tool_schemas.get(tool_name)
        if schema is None:
            return None
        if not _HAS_JSONSCHEMA:
            return None
        try:
            jsonschema.validate(instance=result, schema=schema)
            return None
        except jsonschema.exceptions.ValidationError as e:
            return {
                "tool": tool_name,
                "violation": str(e.message),
                "path": list(e.path),
            }
