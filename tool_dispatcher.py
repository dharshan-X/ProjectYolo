import asyncio
import json
import threading
from typing import Any, Callable, Dict, List, Optional

from session import Session

_AUDIT_REDACTED_KEYS = (
    "api_key",
    "token",
    "secret",
    "password",
    "credential",
    "confirm",
    "content",
    "prompt",
    "audio",
    "image",
)
_ERROR_RESULT_PREFIXES = (
    "error:",
    "error in ",
    "error after ",
    "tool execution error:",
    "mcp execution error:",
)


def _audit_safe_args(arguments: dict) -> dict:
    safe = {}
    for key, value in arguments.items():
        normalized_key = str(key).lower()
        if any(marker in normalized_key for marker in _AUDIT_REDACTED_KEYS):
            safe[key] = "<redacted>"
        elif isinstance(value, str) and len(value) > 500:
            safe[key] = value[:500] + "...<truncated>"
        elif isinstance(value, dict):
            safe[key] = _audit_safe_args(value)
        elif isinstance(value, list) and len(value) > 20:
            safe[key] = ["<redacted: large list>"]
        else:
            try:
                json.dumps(value)
                safe[key] = value
            except (TypeError, ValueError):
                safe[key] = f"<{type(value).__name__}>"
    return safe


def _result_is_error(result: str) -> bool:
    return result.strip().lower().startswith(_ERROR_RESULT_PREFIXES)


async def _run_sync_callable(func: Callable, kwargs: dict) -> Any:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def _settle(setter: Callable, value: Any) -> None:
        # The event loop may have been closed (e.g. during shutdown) while the
        # worker thread was still running. call_soon_threadsafe() raises
        # RuntimeError in that case; swallow it so the thread exits cleanly
        # instead of crashing. The awaiting coroutine is already gone.
        try:
            loop.call_soon_threadsafe(setter, value)
        except RuntimeError:
            pass

    def runner() -> None:
        try:
            result = func(**kwargs)
        except Exception as exc:
            _settle(future.set_exception, exc)
        else:
            _settle(future.set_result, result)

    threading.Thread(target=runner, daemon=True).start()
    return await future


def get_worker_details(task_id: str) -> dict:
    from tools.database_ops import _conn_ctx

    try:
        with _conn_ctx() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT objective, swarm_id FROM background_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                objective, swarm_id = row
                role = ""
                if objective and objective.startswith("[") and "]" in objective:
                    role = objective[1 : objective.find("]")]
                return {"role": role, "swarm_id": swarm_id}
    except Exception:
        pass
    return {"role": "", "swarm_id": None}


async def execute_tool_direct(
    func_name: str,
    func_args: Any,
    user_id: int,
    signal_handler: Optional[Callable] = None,
    session: Any = None,
    call_id: Optional[str] = None,
    confirmed: bool = False,
) -> str:
    from tools.base import audit_log

    if isinstance(func_args, str):
        try:
            func_args = json.loads(func_args)
        except Exception as exc:
            audit_log(
                "tool_call",
                {"user_id": user_id, "name": func_name},
                "error",
                f"Invalid JSON arguments: {exc}",
            )
            return f"Error: Arguments for {func_name} must be a JSON object string or dict. Got: {func_args}"

    if not isinstance(func_args, dict):
        audit_log(
            "tool_call",
            {"user_id": user_id, "name": func_name},
            "error",
            f"Expected object arguments, got {type(func_args).__name__}",
        )
        return f"Error: Invalid arguments for {func_name}; expected object."

    # Never mutate arguments owned by the caller. Contextual values below are
    # trusted runtime data and must replace any model-supplied values.
    func_args = dict(func_args)

    audit_log(
        "tool_call",
        {"user_id": user_id, "name": func_name, "args": _audit_safe_args(func_args)},
        "info",
    )

    async def emit_signal(payload: str) -> Any:
        if not signal_handler:
            return None
        try:
            return await signal_handler(payload)
        except Exception as exc:
            audit_log(
                "tool_signal",
                {"user_id": user_id, "name": func_name},
                "error",
                str(exc),
            )
            return None

    if signal_handler:
        await emit_signal(
            f"__TOOL_CALL__:{json.dumps({'name': func_name, 'args': func_args, 'call_id': call_id}, default=str)}"
        )

    async def _run_with_history_sync(
        tid: str, objective: str, parent_session: Any, orig_handler: Any
    ):
        from agent import run_agent_turn
        from prompt_builder import get_background_initial_messages
        from tools.database_ops import update_background_task_history
        from tools.memory_service import get_memory

        worker_session = Session(
            user_id=parent_session.user_id,
            task_id=tid,
            message_history=get_background_initial_messages(),
            yolo_mode=True,
        )

        async def wrapped_handler(payload):
            update_background_task_history(tid, worker_session.message_history)
            if orig_handler:
                await orig_handler(payload)

        try:
            res = await run_agent_turn(
                objective,
                worker_session,
                signal_handler=wrapped_handler,
                memory_service=get_memory(),
            )
        finally:
            update_background_task_history(tid, worker_session.message_history)
        return res

    import inspect

    from tools.mcp_manager import mcp_manager
    from tools.plugin_manager import PLUGIN_HANDLERS
    from tools.registry import TOOL_REGISTRY

    res = None

    # ── Path 1: MCP tool ──
    if mcp_manager.get_server_for_tool(func_name):
        try:
            res = await mcp_manager.call_tool(func_name, func_args)
        except Exception as e:
            res = f"MCP Execution error: {e}"

    else:
        # ── Path 2: Native / Plugin tool ──
        target = TOOL_REGISTRY.get(func_name) or PLUGIN_HANDLERS.get(func_name)
        if not target and func_name in {"codebase_index", "codebase_search"}:
            import importlib

            importlib.import_module("tools.codebase_ops")
            target = TOOL_REGISTRY.get(func_name)
        if func_name == "compact_conversation":
            from prompt_builder import _compact_history

            target = _compact_history

        if target:
            # Inject standard contextual arguments if the tool signature requires them.
            # For **kwargs tools, replace only context the model actually supplied so
            # tools do not unexpectedly receive new arguments.
            sig = inspect.signature(target)
            accepts_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in sig.parameters.values()
            )

            def accepts_context(name: str) -> bool:
                return name in sig.parameters or (accepts_kwargs and name in func_args)

            if accepts_context("user_id"):
                func_args["user_id"] = user_id
            if accepts_context("session"):
                func_args["session"] = session
            if accepts_context("router"):
                import agent as _agent_mod

                func_args["router"] = getattr(_agent_mod, "router", None)
            if accepts_context("confirm_func"):
                func_args["confirm_func"] = lambda _action, _target: bool(confirmed)

            # Swarm Context Injection
            if func_name in {
                "broadcast_swarm_message",
                "read_swarm_messages",
                "wait_for_swarm_message",
            }:
                if session and session.task_id:
                    details = get_worker_details(session.task_id)
                    if details["swarm_id"]:
                        func_args["swarm_id"] = details["swarm_id"]
                    if "task_id" in sig.parameters:
                        func_args["task_id"] = session.task_id
                    if "role" in sig.parameters and details["role"]:
                        func_args["role"] = details["role"]

            # Special-case injections for complex background task runners
            if (
                func_name == "run_background_mission"
                and "mission_coro" in sig.parameters
            ):
                func_args["mission_coro"] = lambda tid: _run_with_history_sync(
                    tid, func_args.get("objective", ""), session, signal_handler
                )
            elif (
                func_name == "dispatch_parallel_agents"
                and "mission_coro" in sig.parameters
            ):
                func_args["mission_coro"] = lambda obj, tid: _run_with_history_sync(
                    tid, obj, session, signal_handler
                )

            # Retry transient errors
            _TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)
            _MAX_RETRIES = 2
            for _attempt in range(_MAX_RETRIES + 1):
                try:
                    if inspect.iscoroutinefunction(target):
                        res = await target(**func_args)
                    else:
                        res = await _run_sync_callable(target, func_args)
                        if inspect.iscoroutine(res):
                            res = await res
                    break
                except _TRANSIENT_ERRORS as retry_err:
                    if _attempt < _MAX_RETRIES:
                        backoff = (2**_attempt) * 0.5
                        audit_log(
                            "tool_retry",
                            {
                                "user_id": user_id,
                                "name": func_name,
                                "attempt": _attempt + 1,
                            },
                            "error",
                            f"{retry_err}; retrying in {backoff}s",
                        )
                        await asyncio.sleep(backoff)
                    else:
                        res = f"Error after {_MAX_RETRIES + 1} attempts: {retry_err}"
                except Exception as e:
                    res = f"Error in {func_name}: {e}"
                    break
        else:
            # Tool not found in any registry
            await emit_signal(
                f"__TOOL_RESULT__:{json.dumps({'name': func_name, 'result': f'Error: {func_name} not found.', 'call_id': call_id})}"
            )
            audit_log(
                "tool_result",
                {"user_id": user_id, "name": func_name},
                "error",
                "not found",
            )
            return f"Error: {func_name} not found."

    # ── Common result handling for both paths ──
    if res is None:
        res = ""
    if not isinstance(res, str):
        res = str(res)

    await emit_signal(
        f"__TOOL_RESULT__:{json.dumps({'name': func_name, 'result': res, 'call_id': call_id})}"
    )

    if isinstance(res, str) and res.startswith("__SEND_FILE__:"):
        sig_res = await emit_signal(res)
        if sig_res:
            res = sig_res

    audit_log(
        "tool_result",
        {"user_id": user_id, "name": func_name},
        "error" if _result_is_error(res) else "success",
        str(res)[:200] + "..." if len(str(res)) > 200 else str(res),
    )
    return res


def sanitize_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure history strictly complies with LLM tool-call sequence rules."""
    sanitized = []
    i = 0
    while i < len(history):
        msg = history[i]

        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tool_calls = msg.get("tool_calls")
            expected_ids = []
            valid_calls = isinstance(tool_calls, list)

            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    call_id = (
                        tool_call.get("id") if isinstance(tool_call, dict) else None
                    )
                    if (
                        not isinstance(call_id, str)
                        or not call_id.strip()
                        or call_id in expected_ids
                    ):
                        valid_calls = False
                        break
                    expected_ids.append(call_id)

            tool_responses = []
            j = i + 1
            while j < len(history) and history[j].get("role") == "tool":
                tool_responses.append(history[j])
                j += 1

            found_ids = []
            valid_responses = True
            for tool_response in tool_responses:
                response_id = tool_response.get("tool_call_id")
                if (
                    not isinstance(response_id, str)
                    or not response_id.strip()
                    or response_id in found_ids
                ):
                    valid_responses = False
                    break
                found_ids.append(response_id)

            # Require an unambiguous, exact 1:1 match. Sets are safe here only
            # after duplicate and malformed IDs have been rejected.
            sequence_valid = (
                valid_calls
                and valid_responses
                and len(tool_responses) == len(expected_ids)
                and set(expected_ids) == set(found_ids)
            )
            if sequence_valid:
                sanitized.append(msg)
                sanitized.extend(tool_responses)
                i = j
            else:
                # Sequence broken. Strip tool_calls to save text, drop orphaned tool responses
                safe_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                if not safe_msg.get("content"):
                    safe_msg["content"] = (
                        "[Corrupted tool call sequence removed for safety]"
                    )
                sanitized.append(safe_msg)
                i = j
        elif msg.get("role") == "tool":
            i += 1  # Drop stray tool responses
        else:
            sanitized.append(msg)
            i += 1

    return sanitized
