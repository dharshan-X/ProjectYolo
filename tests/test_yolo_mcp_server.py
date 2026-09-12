"""
Tests for ProjectYolo MCP Server (yolo_mcp_server.py).
Verifies tool discovery, schema conformance, and direct execution over MCP protocol.
"""

import pytest
import mcp.types as types
from yolo_mcp_server import handle_list_tools, handle_call_tool, get_mcp_tools


@pytest.mark.anyio
async def test_mcp_server_lists_all_yolo_tools():
    """Verify handle_list_tools returns all registered YOLO tools with valid schemas."""
    tools = await handle_list_tools()
    assert len(tools) >= 100

    tool_names = {t.name for t in tools}
    # Check core capability areas
    assert "memory_search" in tool_names
    assert "working_memory_set" in tool_names
    assert "spawn_worker" in tool_names
    assert "spawn_swarm" in tool_names
    assert "browser_navigate" in tool_names
    assert "gui_mouse_click" in tool_names
    assert "read_user_identity" in tool_names
    assert "list_skills" in tool_names

    # Check schema conformance
    for t in tools:
        assert isinstance(t, types.Tool)
        assert isinstance(t.name, str) and len(t.name) > 0
        assert isinstance(t.description, str)
        assert isinstance(t.inputSchema, dict)
        assert t.inputSchema.get("type") == "object"


@pytest.mark.anyio
async def test_mcp_server_executes_tool_working_memory():
    """Verify handle_call_tool executes working_memory tools cleanly."""
    set_res = await handle_call_tool(
        name="working_memory_set",
        arguments={"key": "project_name", "value": "ProjectYolo"},
    )
    assert len(set_res) == 1
    assert isinstance(set_res[0], types.TextContent)
    assert "project_name" in set_res[0].text or "ProjectYolo" in set_res[0].text or "Stored" in set_res[0].text

    get_res = await handle_call_tool(
        name="working_memory_get",
        arguments={},
    )
    assert len(get_res) == 1
    assert isinstance(get_res[0], types.TextContent)
    assert "ProjectYolo" in get_res[0].text


@pytest.mark.anyio
async def test_mcp_server_executes_identity_and_memory_stats():
    """Verify handle_call_tool can call read_user_identity and memory_stats."""
    id_res = await handle_call_tool(name="read_user_identity", arguments={})
    assert len(id_res) == 1
    assert isinstance(id_res[0], types.TextContent)
    assert len(id_res[0].text) > 0

    stats_res = await handle_call_tool(name="memory_stats", arguments={})
    assert len(stats_res) == 1
    assert isinstance(stats_res[0], types.TextContent)
    assert len(stats_res[0].text) > 0


@pytest.mark.anyio
async def test_mcp_server_handles_tool_execution_error():
    """Verify handle_call_tool gracefully reports unknown tools or execution errors."""
    res = await handle_call_tool(name="non_existent_tool_xyz", arguments={})
    assert len(res) == 1
    assert isinstance(res[0], types.TextContent)
    assert "Error" in res[0].text or "unknown" in res[0].text.lower() or "not found" in res[0].text.lower()


@pytest.mark.anyio
async def test_mcp_server_end_to_end_client_handshake():
    """Verify full end-to-end stdio MCP client connection, tool enumeration, and tool execution."""
    import sys
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["yolo_mcp_server.py"],
        env=None,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init_res = await session.initialize()
            assert init_res.serverInfo.name == "yolo"

            tools_res = await session.list_tools()
            assert len(tools_res.tools) >= 100

            tool_names = [t.name for t in tools_res.tools]
            assert "memory_stats" in tool_names
            assert "read_user_identity" in tool_names

            call_res = await session.call_tool("read_user_identity", arguments={})
            assert len(call_res.content) == 1
            assert isinstance(call_res.content[0], types.TextContent)
            assert len(call_res.content[0].text) > 0
