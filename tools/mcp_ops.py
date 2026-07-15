import asyncio
import shlex

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools.base import audit_log
from tools.mcp_manager import MCP_TOOL_CALL_TIMEOUT_SECONDS, _build_mcp_env
from tools.registry import register_tool


def _parse_server_command(server_command: str) -> list[str]:
    parts = shlex.split(server_command)
    if not parts:
        raise ValueError("server_command cannot be empty")
    return parts


def _normalize_mcp_result_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        normalized = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                normalized.append(str(text))
            else:
                normalized.append(str(item))
        return "\n".join(normalized)
    return str(content)


@register_tool()
async def mcp_run_tool(server_command: str, tool_name: str, tool_args: dict) -> str:
    """Connect to an MCP server and execute a tool."""
    try:
        cmd_parts = _parse_server_command(server_command)
        server_params = StdioServerParameters(
            command=cmd_parts[0], args=cmd_parts[1:], env=_build_mcp_env({})
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List tools first to verify existence (optional but safer)
                # tools = await session.list_tools()

                result = await asyncio.wait_for(
                    session.call_tool(tool_name, tool_args),
                    timeout=MCP_TOOL_CALL_TIMEOUT_SECONDS,
                )

                output = _normalize_mcp_result_content(result.content)
                audit_log(
                    "mcp_run_tool",
                    {"server": server_command, "tool": tool_name},
                    "success",
                )
                return output

    except asyncio.TimeoutError:
        detail = f"Tool call timed out after {MCP_TOOL_CALL_TIMEOUT_SECONDS}s"
        audit_log(
            "mcp_run_tool",
            {"server": server_command, "tool": tool_name},
            "error",
            detail,
        )
        return f"Error executing MCP tool: {detail}"
    except Exception as e:
        audit_log(
            "mcp_run_tool",
            {"server": server_command, "tool": tool_name},
            "error",
            str(e),
        )
        return f"Error executing MCP tool: {e}"


@register_tool()
async def mcp_list_tools(server_command: str) -> str:
    """List all tools provided by a specific MCP server."""
    try:
        cmd_parts = _parse_server_command(server_command)
        server_params = StdioServerParameters(
            command=cmd_parts[0], args=cmd_parts[1:], env=_build_mcp_env({})
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()

                tool_list = [f"• {t.name}: {t.description}" for t in tools.tools]
                audit_log("mcp_list_tools", {"server": server_command}, "success")
                return f"Tools available on server `{server_command}`:\n" + "\n".join(
                    tool_list
                )

    except Exception as e:
        audit_log("mcp_list_tools", {"server": server_command}, "error", str(e))
        return f"Error listing MCP tools: {e}"
