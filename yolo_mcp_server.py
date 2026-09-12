#!/usr/bin/env python3
"""
ProjectYolo MCP Server
Exposes YOLO's native cognitive tooling (Tiered Memory, GUI Perception, Swarm Orchestration,
Deep Research, Browser Control, etc.) as a standard Model Context Protocol (MCP) server
for Codex, Claude Desktop, Cursor, and any MCP-compatible client.
"""

import asyncio
import io
import json
import logging
import os
import sys
from io import TextIOWrapper
from typing import Any, Dict, List, Optional

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# Import YOLO components
import tools
from tools import TOOLS_SCHEMAS
from tool_dispatcher import execute_tool_direct
from session import Session

# Configure logging strictly to stderr to keep stdout pure for JSON-RPC
logging.basicConfig(
    level=logging.INFO,
    format="[yolo-mcp] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("yolo-mcp")

# Initialize MCP Server
app = Server("yolo")


def get_mcp_tools() -> List[types.Tool]:
    """Convert YOLO TOOLS_SCHEMAS into MCP Tool objects."""
    tools_list: List[types.Tool] = []
    for s in TOOLS_SCHEMAS:
        fn = s.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        desc = fn.get("description") or f"YOLO tool {name}"
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        tools_list.append(
            types.Tool(
                name=name,
                description=desc,
                inputSchema=params,
            )
        )
    return tools_list


@app.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """Handle tools/list request from MCP client."""
    return get_mcp_tools()


@app.call_tool()
async def handle_call_tool(
    name: str, arguments: Optional[Dict[str, Any]] = None
) -> List[types.TextContent]:
    """Handle tools/call request from MCP client."""
    args = arguments or {}

    # Defensive prefix stripping: Codex or clients may pass mcp__yolo__tool or yolo__tool
    clean_name = name
    if clean_name.startswith("mcp__yolo__"):
        clean_name = clean_name[len("mcp__yolo__"):]
    elif clean_name.startswith("yolo__"):
        clean_name = clean_name[len("yolo__"):]
    elif clean_name.startswith("mcp__"):
        parts = clean_name.split("__", 2)
        if len(parts) == 3:
            clean_name = parts[2]

    logger.info("Executing tool: %s (resolved: %s) with args: %s", name, clean_name, list(args.keys()))

    # Ephemeral session with yolo_mode=True for autonomous execution without interactive prompts
    session = Session(user_id=1, message_history=[], yolo_mode=True)

    try:
        result = await execute_tool_direct(
            func_name=clean_name,
            func_args=args,
            user_id=1,
            session=session,
            confirmed=True,
        )
        if isinstance(result, (dict, list)):
            res_text = json.dumps(result, indent=2)
        else:
            res_text = str(result)
        return [types.TextContent(type="text", text=res_text)]
    except Exception as exc:
        logger.error("Error executing tool %s (%s): %s", name, clean_name, exc)
        return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]


async def run_server():
    """Run MCP server over standard input/output."""
    # Capture raw stdout buffer for MCP JSON-RPC protocol before any tool prints to stdout
    out_wrapper = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))
    sys.stdout = sys.stderr

    logger.info("Starting YOLO MCP server (%d tools registered)", len(TOOLS_SCHEMAS))
    async with stdio_server(stdout=out_wrapper) as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        # Helper to inspect tools from CLI
        tool_names = [s.get("function", {}).get("name") for s in TOOLS_SCHEMAS]
        print(json.dumps({"count": len(tool_names), "tools": tool_names}, indent=2))
        return

    try:
        asyncio.run(run_server())
    except (KeyboardInterrupt, SystemExit):
        logger.info("YOLO MCP server stopped.")


if __name__ == "__main__":
    main()
