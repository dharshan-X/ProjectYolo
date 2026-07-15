import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tool_dispatcher import execute_tool_direct, sanitize_history
from tools import mcp_ops
from tools.mcp_manager import MCPManager
from tools.registry import TOOL_REGISTRY


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _new_manager() -> MCPManager:
    manager = object.__new__(MCPManager)
    manager._initialized = False
    MCPManager.__init__(manager)
    return manager


@pytest.mark.asyncio
async def test_dispatcher_overrides_untrusted_context_without_mutating_input():
    captured = {}
    trusted_session = object()
    trusted_router = object()

    def untrusted_confirm(_action, _target):
        return False

    caller_args = {
        "user_id": 999,
        "session": "model-session",
        "router": "model-router",
        "confirm_func": untrusted_confirm,
    }
    original_args = dict(caller_args)

    async def contextual_tool(user_id, session, router, confirm_func):
        captured.update(
            user_id=user_id,
            session=session,
            router=router,
            confirmed=confirm_func("write", "target"),
        )
        return "ok"

    with (
        patch.dict(
            TOOL_REGISTRY,
            {"security_contextual_tool": contextual_tool},
            clear=False,
        ),
        patch("agent.router", trusted_router),
    ):
        result = await execute_tool_direct(
            "security_contextual_tool",
            caller_args,
            user_id=42,
            session=trusted_session,
            confirmed=True,
        )

    assert result == "ok"
    assert captured == {
        "user_id": 42,
        "session": trusted_session,
        "router": trusted_router,
        "confirmed": True,
    }
    assert caller_args == original_args


@pytest.mark.asyncio
async def test_dispatcher_overrides_model_context_accepted_by_kwargs():
    captured = {}
    trusted_session = object()
    trusted_router = object()
    caller_args = {
        "user_id": 999,
        "session": "model-session",
        "router": "model-router",
        "confirm_func": "model-confirm",
        "ordinary": "unchanged",
    }

    async def kwargs_tool(**kwargs):
        captured.update(kwargs)
        return "ok"

    with (
        patch.dict(
            TOOL_REGISTRY,
            {"security_kwargs_tool": kwargs_tool},
            clear=False,
        ),
        patch("agent.router", trusted_router),
    ):
        result = await execute_tool_direct(
            "security_kwargs_tool",
            caller_args,
            user_id=42,
            session=trusted_session,
            confirmed=True,
        )

    assert result == "ok"
    assert captured["user_id"] == 42
    assert captured["session"] is trusted_session
    assert captured["router"] is trusted_router
    assert captured["confirm_func"]("write", "target") is True
    assert captured["ordinary"] == "unchanged"
    assert caller_args["user_id"] == 999
    assert caller_args["session"] == "model-session"
    assert caller_args["router"] == "model-router"
    assert caller_args["confirm_func"] == "model-confirm"


@pytest.mark.asyncio
async def test_dispatcher_audits_invalid_arguments_and_redacts_sensitive_values():
    async def failing_tool(**_kwargs):
        return "Error: execution failed"

    with (
        patch.dict(TOOL_REGISTRY, {"audit_security_tool": failing_tool}, clear=False),
        patch("tools.base.audit_log") as audit,
    ):
        invalid_result = await execute_tool_direct(
            "audit_security_tool", "{invalid", user_id=42
        )
        result = await execute_tool_direct(
            "audit_security_tool",
            {
                "api_key": "top-secret",
                "content": "private file body",
                "ordinary": "visible",
            },
            user_id=42,
        )

    assert invalid_result.startswith("Error: Arguments")
    assert result == "Error: execution failed"
    invalid_audit = audit.call_args_list[0]
    assert invalid_audit.args[2] == "error"
    call_audit = next(
        call
        for call in audit.call_args_list
        if call.args[0] == "tool_call" and call.args[2] == "info"
    )
    assert call_audit.args[1]["args"] == {
        "api_key": "<redacted>",
        "content": "<redacted>",
        "ordinary": "visible",
    }
    result_audit = next(
        call for call in audit.call_args_list if call.args[0] == "tool_result"
    )
    assert result_audit.args[2] == "error"


@pytest.mark.asyncio
async def test_result_signal_failure_does_not_change_tool_outcome():
    calls = 0

    async def side_effect_tool():
        nonlocal calls
        calls += 1
        return "completed"

    async def broken_signal(payload):
        if payload.startswith("__TOOL_RESULT__"):
            raise RuntimeError("UI disconnected")

    with (
        patch.dict(
            TOOL_REGISTRY, {"signal_security_tool": side_effect_tool}, clear=False
        ),
        patch("tools.base.audit_log") as audit,
    ):
        result = await execute_tool_direct(
            "signal_security_tool", {}, user_id=42, signal_handler=broken_signal
        )

    assert result == "completed"
    assert calls == 1
    assert any(call.args[0] == "tool_signal" for call in audit.call_args_list)


@pytest.mark.parametrize(
    "tool_calls,tool_responses",
    [
        ([{"function": {"name": "missing_id"}}], []),
        ([{"id": "duplicate"}, {"id": "duplicate"}], []),
        ([{"id": None}], []),
        ([{"id": "valid"}], [{"role": "tool", "content": "missing id"}]),
        (
            [{"id": "valid"}],
            [
                {"role": "tool", "tool_call_id": "valid", "content": "one"},
                {"role": "tool", "tool_call_id": "valid", "content": "two"},
            ],
        ),
    ],
)
def test_sanitize_history_rejects_missing_duplicate_and_malformed_ids(
    tool_calls, tool_responses
):
    history = [{"role": "assistant", "tool_calls": tool_calls}, *tool_responses]

    sanitized = sanitize_history(history)

    assert len(sanitized) == 1
    assert sanitized[0]["role"] == "assistant"
    assert "tool_calls" not in sanitized[0]
    assert "Corrupted tool call sequence" in sanitized[0]["content"]


@pytest.mark.asyncio
async def test_mcp_list_tools_uses_sanitized_environment():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(
        return_value=SimpleNamespace(
            tools=[SimpleNamespace(name="remote", description="Remote tool")]
        )
    )
    server_params = object()

    with (
        patch.object(
            mcp_ops, "_build_mcp_env", return_value={"PATH": "/safe"}
        ) as build_env,
        patch.object(
            mcp_ops, "StdioServerParameters", return_value=server_params
        ) as params_type,
        patch.object(
            mcp_ops, "stdio_client", return_value=_AsyncContext(("read", "write"))
        ),
        patch.object(mcp_ops, "ClientSession", return_value=_AsyncContext(session)),
        patch.object(mcp_ops, "audit_log") as audit,
    ):
        result = await mcp_ops.mcp_list_tools("server --flag")

    build_env.assert_called_once_with({})
    params_type.assert_called_once_with(
        command="server", args=["--flag"], env={"PATH": "/safe"}
    )
    audit.assert_called_once_with(
        "mcp_list_tools", {"server": "server --flag"}, "success"
    )
    assert "remote" in result


@pytest.mark.asyncio
async def test_direct_mcp_tool_call_uses_sanitized_env_and_times_out():
    cancelled = asyncio.Event()

    async def blocked_call(_tool_name, _tool_args):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    session = MagicMock()
    session.initialize = AsyncMock()
    session.call_tool = blocked_call

    with (
        patch.object(mcp_ops, "MCP_TOOL_CALL_TIMEOUT_SECONDS", 0.01),
        patch.object(
            mcp_ops, "_build_mcp_env", return_value={"PATH": "/safe"}
        ) as build_env,
        patch.object(
            mcp_ops, "stdio_client", return_value=_AsyncContext(("read", "write"))
        ),
        patch.object(mcp_ops, "ClientSession", return_value=_AsyncContext(session)),
        patch.object(mcp_ops, "audit_log") as audit,
    ):
        result = await mcp_ops.mcp_run_tool("server", "slow", {})

    build_env.assert_called_once_with({})
    assert cancelled.is_set()
    assert "timed out after 0.01s" in result
    assert audit.call_args.args[2] == "error"


@pytest.mark.asyncio
async def test_mcp_native_name_collision_is_namespaced():
    manager = _new_manager()
    native_tool = MagicMock()
    remote_tool = SimpleNamespace(
        name="native_collision",
        description="remote",
        inputSchema={"type": "object", "properties": {}},
    )
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[remote_tool]))

    with (
        patch.dict(TOOL_REGISTRY, {"native_collision": native_tool}, clear=False),
        patch(
            "tools.mcp_manager.stdio_client",
            return_value=_AsyncContext(("read", "write")),
        ),
        patch(
            "tools.mcp_manager.ClientSession",
            return_value=_AsyncContext(session),
        ),
        patch("tools.mcp_manager.audit_log"),
    ):
        await manager._connect_server("remote_server", MagicMock())

        exposed_name = manager.tool_schemas[0]["function"]["name"]
        assert exposed_name == "remote_server__native_collision"
        assert manager.get_server_for_tool("native_collision") is None
        assert manager.get_server_for_tool(exposed_name) == "remote_server"
        assert manager._tool_to_original_name[exposed_name] == "native_collision"

        await manager.cleanup()


@pytest.mark.asyncio
async def test_mcp_initialize_is_single_flight_and_cleanup_allows_reconnect():
    manager = _new_manager()
    connect_started = asyncio.Event()
    release_connect = asyncio.Event()

    def load_config():
        manager.servers = {"remote": {"command": "server"}}
        return True

    async def connect_server(_server_name, _server_params):
        connect_started.set()
        await release_connect.wait()

    with (
        patch.object(manager, "load_config", side_effect=load_config),
        patch.object(manager, "_connect_server", side_effect=connect_server) as connect,
    ):
        first = asyncio.create_task(manager.initialize())
        await connect_started.wait()
        second = asyncio.create_task(manager.initialize())
        release_connect.set()
        await asyncio.gather(first, second)

        assert connect.await_count == 1
        assert manager._connections_initialized is True

        await manager.cleanup()
        assert manager._connections_initialized is False

        await manager.initialize()
        assert connect.await_count == 2
        assert manager._connections_initialized is True


@pytest.mark.asyncio
async def test_failed_mcp_initialization_is_retryable():
    manager = _new_manager()

    def load_config():
        manager.servers = {"remote": {"command": "server"}}
        return True

    with (
        patch.object(manager, "load_config", side_effect=load_config),
        patch.object(
            manager,
            "_connect_server",
            new=AsyncMock(side_effect=[RuntimeError("unavailable"), None]),
        ) as connect,
        patch("tools.mcp_manager.audit_log"),
    ):
        await manager.initialize()
        assert manager._connections_initialized is False

        await manager.initialize()
        assert manager._connections_initialized is True
        assert connect.await_count == 2


@pytest.mark.asyncio
async def test_managed_mcp_tool_call_times_out():
    manager = _new_manager()
    cancelled = asyncio.Event()

    async def blocked_call(_tool_name, _args):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    session = MagicMock()
    session.call_tool = blocked_call
    manager.sessions["remote"] = session
    manager._tool_to_server["remote_timeout_tool"] = "remote"
    manager._tool_to_original_name["remote_timeout_tool"] = "slow"

    with (
        patch("tools.mcp_manager.MCP_TOOL_CALL_TIMEOUT_SECONDS", 0.01),
        patch("tools.mcp_manager.audit_log") as audit,
    ):
        result = await manager.call_tool("remote_timeout_tool", {})

    assert cancelled.is_set()
    assert "timed out after 0.01s" in result
    assert audit.call_args.args[2] == "error"
