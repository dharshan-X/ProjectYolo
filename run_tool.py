#!/usr/bin/env python3
"""YOLO Tool CLI Runner — Dispatches YOLO tools safely from external environments (e.g. Codex sandbox)."""
import asyncio
import json
import os
import sys
from pathlib import Path

# Fix sys.path to strictly prioritize ProjectYolo and remove caller cwd
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
while "" in sys.path:
    sys.path.remove("")
while "." in sys.path:
    sys.path.remove(".")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_tool.py <tool_name> [json_args]")
        sys.exit(1)

    tool_name = sys.argv[1]
    args = {}
    if len(sys.argv) >= 3:
        raw_args = sys.argv[2]
        try:
            parsed = json.loads(raw_args)
            if isinstance(parsed, dict):
                args = parsed
            else:
                args = {"query": str(parsed)}
        except Exception:
            args = {"query": raw_args}

    # Normalize tool name (strip prefixes)
    if tool_name.startswith("mcp__yolo__"):
        tool_name = tool_name[len("mcp__yolo__") :]
    elif tool_name.startswith("yolo__"):
        tool_name = tool_name[len("yolo__") :]

    try:
        from tool_dispatcher import execute_tool_direct
        from session import Session
        session = Session(user_id=1, message_history=[], yolo_mode=True)
        result = asyncio.run(
            execute_tool_direct(
                tool_name,
                args,
                user_id=1,
                session=session,
                confirmed=True,
            )
        )
        print(result)
    except Exception as e:
        print(f"Error executing {tool_name}: {e}")

if __name__ == "__main__":
    main()
