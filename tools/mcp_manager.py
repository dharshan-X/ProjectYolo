import asyncio
import json
import math
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from tools.base import YOLO_HOME, audit_log
from tools.registry import TOOL_REGISTRY, register_tool

MCP_CONFIG_PATH = YOLO_HOME / "mcp_servers.json"


def _read_positive_timeout(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


MCP_CONNECT_TIMEOUT_SECONDS = _read_positive_timeout("MCP_CONNECT_TIMEOUT_SECONDS", 2.0)
MCP_TOOL_CALL_TIMEOUT_SECONDS = _read_positive_timeout(
    "MCP_TOOL_CALL_TIMEOUT_SECONDS", 30.0
)

# Substrings that mark an env var as a secret. Such vars are NOT inherited by
# MCP subprocesses (which may be third-party/untrusted) unless explicitly
# re-supplied via a server's own `env` config. This prevents leaking every
# provider API key to every MCP server. Set MCP_INHERIT_ALL_ENV=true to opt
# back into inheriting the full parent environment.
_MCP_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL")


def _build_mcp_env(server_env: dict) -> dict:
    """Build the subprocess environment for an MCP server.

    Inherits the parent environment but strips secret-looking variables, then
    layers the server's explicitly-configured `env` on top (so a server can
    still receive a secret it actually needs)."""
    if os.getenv("MCP_INHERIT_ALL_ENV", "false").lower() == "true":
        merged = os.environ.copy()
    else:
        merged = {
            k: v
            for k, v in os.environ.items()
            if not any(marker in k.upper() for marker in _MCP_SECRET_MARKERS)
        }
    merged.update(server_env or {})
    return merged


class MCPManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.servers: Dict[str, dict] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self._server_tasks: List[asyncio.Task] = []
        self.tool_schemas: List[Dict[str, Any]] = []
        self._tool_to_server: Dict[str, str] = {}
        self._tool_to_original_name: Dict[str, str] = {}
        self._connections_initialized = False
        self._initialization_task: Optional[asyncio.Task] = None
        self._initialization_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._initialized = True

    def load_config(self) -> bool:
        if not MCP_CONFIG_PATH.exists():
            with open(MCP_CONFIG_PATH, "w") as f:
                json.dump({"mcpServers": {}}, f, indent=4)
            self.servers = {}
            return True

        try:
            with open(MCP_CONFIG_PATH, "r") as f:
                data = json.load(f)
                self.servers = data.get("mcpServers", {})
            return True
        except Exception as e:
            audit_log(
                "mcp_manager",
                {"path": str(MCP_CONFIG_PATH)},
                "error",
                f"Failed to load config: {e}",
            )
            return False

    async def initialize(self):
        """Connect to configured servers once, sharing work across callers."""
        if self._connections_initialized:
            return

        async with self._initialization_lock:
            if self._connections_initialized:
                return
            task = self._initialization_task
            if task is None:
                task = asyncio.create_task(self._initialize_connections())
                self._initialization_task = task

                def clear_initialization_task(done_task: asyncio.Task) -> None:
                    if self._initialization_task is done_task:
                        self._initialization_task = None

                task.add_done_callback(clear_initialization_task)

        try:
            await asyncio.shield(task)
        finally:
            if task.done():
                async with self._initialization_lock:
                    if self._initialization_task is task:
                        self._initialization_task = None

    async def _initialize_connections(self) -> None:
        async with self._lifecycle_lock:
            self._connections_initialized = False
            if not self.load_config():
                return

            # Preserve successful partial connections while retrying only servers
            # that failed during an earlier initialization attempt.
            if not self.sessions:
                self.tool_schemas.clear()
                self._tool_to_server.clear()
                self._tool_to_original_name.clear()

            failed = False
            for server_name, server_info in self.servers.items():
                command = server_info.get("command")
                url = server_info.get("url")

                if (not command and not url) or server_name in self.sessions:
                    continue

                if command:
                    args = server_info.get("args", [])
                    env = server_info.get("env", {})
                    server_params = StdioServerParameters(
                        command=command,
                        args=args,
                        env=_build_mcp_env(env),
                    )
                else:
                    server_params = {
                        "url": url,
                        "headers": server_info.get("headers", {})
                    }

                try:
                    await self._connect_server(server_name, server_params)
                except Exception as e:
                    failed = True
                    audit_log(
                        "mcp_manager",
                        {"server": server_name},
                        "error",
                        f"Failed to connect: {repr(e)}",
                    )

            self._connections_initialized = not failed

    async def _connect_server(
        self, server_name: str, server_params: Union[StdioServerParameters, dict]
    ) -> None:
        ready_event = asyncio.Event()
        error_container = []

        async def connection_task():
            server_stack = AsyncExitStack()
            try:
                if isinstance(server_params, StdioServerParameters):
                    context = stdio_client(server_params)
                else:
                    context = sse_client(url=server_params["url"], headers=server_params.get("headers"))

                read_stream, write_stream = await asyncio.wait_for(
                    server_stack.enter_async_context(context),
                    timeout=MCP_CONNECT_TIMEOUT_SECONDS,
                )
                session = await asyncio.wait_for(
                    server_stack.enter_async_context(
                        ClientSession(read_stream, write_stream)
                    ),
                    timeout=MCP_CONNECT_TIMEOUT_SECONDS,
                )

                await asyncio.wait_for(
                    session.initialize(),
                    timeout=MCP_CONNECT_TIMEOUT_SECONDS,
                )
                tools = await asyncio.wait_for(
                    session.list_tools(),
                    timeout=MCP_CONNECT_TIMEOUT_SECONDS,
                )

                self.sessions[server_name] = session

                for t in tools.tools:
                    tool_name = t.name
                    collision_detail = None
                    if tool_name in TOOL_REGISTRY:
                        collision_detail = "a native tool"
                    elif tool_name in self._tool_to_server:
                        collision_detail = (
                            f"MCP server '{self._tool_to_server[tool_name]}'"
                        )

                    if collision_detail:
                        base_name = f"{server_name}__{t.name}"
                        tool_name = base_name
                        suffix = 2
                        while (
                            tool_name in TOOL_REGISTRY
                            or tool_name in self._tool_to_server
                        ):
                            tool_name = f"{base_name}__{suffix}"
                            suffix += 1
                        audit_log(
                            "mcp_manager",
                            {"server": server_name, "tool": t.name},
                            "warning",
                            f"Tool name collision with {collision_detail}; exposed as '{tool_name}'.",
                        )
                    schema = {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": f"[MCP: {server_name}] {t.description or ''}",
                            "parameters": t.inputSchema
                            or {"type": "object", "properties": {}},
                        },
                    }
                    self.tool_schemas.append(schema)
                    self._tool_to_server[tool_name] = server_name
                    self._tool_to_original_name[tool_name] = t.name

                audit_log(
                    "mcp_manager",
                    {"server": server_name},
                    "success",
                    "Connected and loaded tools",
                )

                ready_event.set()

                # Keep the stack open forever until task is cancelled
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

            except Exception as e:
                error_container.append(e)
                ready_event.set()
            finally:
                try:
                    await server_stack.aclose()
                except Exception:
                    pass

        task = asyncio.create_task(connection_task())
        try:
            await ready_event.wait()
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

        if error_container:
            raise error_container[0]

        if not hasattr(self, "_server_tasks"):
            self._server_tasks = []
        self._server_tasks.append(task)

    async def cleanup(self):
        """Close all connections and allow a later initialize() to reconnect."""
        self._connections_initialized = False
        async with self._lifecycle_lock:
            for task in getattr(self, "_server_tasks", []):
                task.cancel()

            if hasattr(self, "_server_tasks") and self._server_tasks:
                await asyncio.gather(*self._server_tasks, return_exceptions=True)

            self._server_tasks = []
            self.sessions.clear()
            self.tool_schemas.clear()
            self._tool_to_server.clear()
            self._tool_to_original_name.clear()
            self._connections_initialized = False

    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        if tool_name in TOOL_REGISTRY:
            return None
        return self._tool_to_server.get(tool_name)

    async def call_tool(self, tool_name: str, args: dict) -> str:
        server_name = self.get_server_for_tool(tool_name)
        if not server_name:
            raise ValueError(f"No MCP server found for tool: {tool_name}")

        session = self.sessions.get(server_name)
        if not session:
            raise ValueError(f"MCP server {server_name} is not connected")

        try:
            original_name = getattr(self, "_tool_to_original_name", {}).get(
                tool_name, tool_name
            )
            result = await asyncio.wait_for(
                session.call_tool(original_name, args),
                timeout=MCP_TOOL_CALL_TIMEOUT_SECONDS,
            )

            # Normalize result
            if isinstance(result.content, str):
                return result.content
            if isinstance(result.content, list):
                normalized = []
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text is not None:
                        normalized.append(str(text))
                    else:
                        normalized.append(str(item))
                return "\n".join(normalized)
            return str(result.content)

        except asyncio.TimeoutError:
            detail = f"Tool call timed out after {MCP_TOOL_CALL_TIMEOUT_SECONDS}s"
            audit_log(
                "mcp_manager_call",
                {"server": server_name, "tool": tool_name},
                "error",
                detail,
            )
            return f"Error executing MCP tool {tool_name}: {detail}"
        except Exception as e:
            audit_log(
                "mcp_manager_call",
                {"server": server_name, "tool": tool_name},
                "error",
                str(e),
            )
            return f"Error executing MCP tool {tool_name}: {e}"


# Global instance
mcp_manager = MCPManager()


@register_tool("list_mcp_servers")
async def list_mcp_servers() -> str:
    """Lists all configured MCP servers and their current connection status."""
    manager = mcp_manager
    await manager.initialize()  # Ensure initialized

    if not manager.servers:
        return "No MCP servers configured."

    lines = ["Configured MCP Servers:"]
    for name, config in manager.servers.items():
        status = "Connected" if name in manager.sessions else "Disconnected/Error"
        tool_count = len([t for t, s in manager._tool_to_server.items() if s == name])
        lines.append(f"- {name}: {status} ({tool_count} tools)")
        if config.get("command"):
            lines.append(
                f"  Command: {config.get('command')} {' '.join(config.get('args', []))}"
            )
        elif config.get("url"):
            lines.append(f"  URL: {config.get('url')}")

    return "\n".join(lines)
