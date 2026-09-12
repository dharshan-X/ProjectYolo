#!/usr/bin/env python3
"""
Yolo as Model Server — OpenAI-Compatible API
Exposes Yolo's full agent loop as an OpenAI-compatible model endpoint.

Allows Claude Code, Codex, Cursor, Opencode, etc. to use Yolo as their LLM:

  Codex:  ~/.codex/config.toml
    [model_providers.yolo]
    base_url = "http://127.0.0.1:8788/v1"
    api_key = "yolo-local"

  Claude: ANTHROPIC_BASE_URL=http://127.0.0.1:8788/v1 ANTHROPIC_API_KEY=yolo-local

Endpoints:
  GET  /v1/models
  POST /v1/chat/completions  (supports stream: true)
  POST /v1/messages          (Anthropic compat, translates to chat/completions)
  GET  /health, GET /v1/health

Opaque agent mode: Yolo executes its own 60+ tools internally (yolo_mode=True),
caller receives final text only. Incoming `tools` from caller are ignored
unless YOLO_MODEL_TOOL_PASSTHROUGH=true.

Refs:
  - desktop/api_bridge.py:333 handle_chat_stream (SSE pattern)
  - agent.py:830 run_agent_turn (core loop)
  - llm_router.py:246 router.config.model
  - session.py:45 SessionManager
"""
import asyncio
import hmac
import json
import os
import sys
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Ensure project root on path when run as script
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.settings import load_settings
load_settings()

from aiohttp import web

import agent as yolo_agent
from session import Session, SessionManager

# ── Config ──
YOLO_MODEL_PORT = int(os.getenv("YOLO_MODEL_PORT", "8788"))
YOLO_MODEL_HOST = os.getenv("YOLO_MODEL_HOST", "127.0.0.1")
YOLO_MODEL_DISABLE_AUTH = os.getenv("YOLO_MODEL_DISABLE_AUTH", "false").lower() == "true"
# Comma-separated API keys; if empty and auth not disabled, "yolo-local" is accepted (dev)
_YOLO_MODEL_API_KEYS_RAW = os.getenv("YOLO_MODEL_API_KEYS", "").strip()
YOLO_MODEL_TOOL_PASSTHROUGH = os.getenv("YOLO_MODEL_TOOL_PASSTHROUGH", "false").lower() == "true"

TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
session_manager: Optional[SessionManager] = None  # type: ignore


def _get_allowed_keys() -> List[str]:
    if not _YOLO_MODEL_API_KEYS_RAW:
        return ["yolo-local", "sk-yolo-local", "not-required"]
    return [k.strip() for k in _YOLO_MODEL_API_KEYS_RAW.split(",") if k.strip()]


def _extract_bearer_token(request: web.Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    # Also allow X-Yolo-Bridge-Token / api_key query
    token = request.headers.get("X-Yolo-Bridge-Token", "").strip()
    if token:
        return token
    token = request.query.get("token", "").strip()
    if token:
        return token
    # x-api-key for Anthropic
    token = request.headers.get("x-api-key", "").strip()
    if token:
        return token
    return ""


def _is_authorized(request: web.Request) -> bool:
    if YOLO_MODEL_DISABLE_AUTH:
        return True
    token = _extract_bearer_token(request)
    if not token:
        return False
    allowed = _get_allowed_keys()
    return any(hmac.compare_digest(token, k) for k in allowed)


def _api_key_to_user_id(api_key: str) -> int:
    """Deterministic user_id per API key (for per-key session isolation)."""
    if not api_key:
        return 1
    h = hashlib.sha256(api_key.encode()).hexdigest()
    # 1..2_000_000 range
    return (int(h[:8], 16) % 2000000) + 1


def _get_text_content(content: Any) -> str:
    """Extract text from OpenAI content (str or list of {type:text})."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "input_text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return " ".join(parts).strip()
    return str(content) if content is not None else ""


def _normalize_incoming_messages(raw_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map OpenAI messages to Yolo history format (pass-through for run_agent_turn)."""
    normalized: List[Dict[str, Any]] = []
    for m in raw_messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        # content may be str or list
        if isinstance(content, list):
            content = _get_text_content(content)
        elif content is None:
            content = ""
        else:
            content = str(content)
        entry: Dict[str, Any] = {"role": role, "content": content}
        if m.get("tool_calls"):
            entry["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
            entry["name"] = m.get("name", "")
        normalized.append(entry)
    return normalized


def _build_yolo_session(
    *,
    user_id: int,
    incoming_messages: List[Dict[str, Any]],
    model_name: str,
    client_tools: Optional[List[Dict[str, Any]]] = None,
) -> tuple[Session, Any]:
    """
    Build an ephemeral Session for a single model request.
    - Starts with Yolo's system prompt (prompt_builder.get_initial_messages)
    - Appends all incoming messages except the last user message (which becomes user_msg)
    - Returns (session, user_msg) where user_msg may be str or list (multimodal passthrough kept as str)
    """
    from prompt_builder import get_initial_messages

    # Determine yolo_mode / think_mode from model alias
    yolo_mode = True  # model server is autonomous; avoid HITL
    think_mode = False
    think_policy = "auto"
    # model aliases: yolo, yolo-think, yolo-yolo, yolo-safe
    lower_model = (model_name or "yolo").lower()
    if "think" in lower_model:
        think_mode = True
        think_policy = "force_on"
    if "safe" in lower_model:
        yolo_mode = False

    yolo_system = get_initial_messages()[0]  # {"role":"system","content":...}
    normalized = _normalize_incoming_messages(incoming_messages)

    if not normalized:
        # No messages -> create session with just system
        session = Session(user_id=user_id, message_history=[yolo_system], yolo_mode=yolo_mode)
        session.think_mode = think_mode
        session.think_mode_policy = think_policy
        session.client_tools = client_tools or []
        return session, "Hello"

    # Last message is the current user turn
    last_msg = normalized[-1]
    prior = normalized[:-1]

    # History = yolo_system + prior (client's history without last turn)
    history: List[Dict[str, Any]] = [yolo_system]
    # Prior may contain client's system messages; they become legacy appendices via _normalize_single_system_message
    history.extend(prior)

    session = Session(user_id=user_id, message_history=history, yolo_mode=yolo_mode)
    session.think_mode = think_mode
    session.think_mode_policy = think_policy
    session.client_tools = client_tools or []

    # Last message content is user_msg; handle tool role edge
    if last_msg.get("role") == "tool":
        has_preceding_assistant_call = any(
            m.get("role") == "assistant" and any(
                tc.get("id") == last_msg.get("tool_call_id")
                for tc in (m.get("tool_calls") or [])
                if isinstance(tc, dict)
            )
            for m in prior
        )
        if has_preceding_assistant_call:
            history.append(last_msg)
            user_msg = None
        else:
            user_msg = _get_text_content(last_msg.get("content", ""))
    else:
        user_msg = last_msg.get("content", "")
        # If last_msg has tool_calls already, we keep it in history and set user_msg to content
        # The agent loop will handle it via _find_unanswered_tool_calls

    # If last message already contains tool_calls (client wants passthrough), keep it in history
    # and let run_agent_turn's unanswered tool handling process it. For opaque mode we treat
    # last content as prompt.
    return session, user_msg


async def _route_or_execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    session: Any,
    signal_handler: Optional[Callable[[str], Awaitable[None]]] = None,
    call_id: Optional[str] = None,
    confirmed: Optional[bool] = None,
) -> str:
    """
    Routes a tool execution request.
    If the tool is in session.client_tools, emits YOLO_CLIENT_TOOL: signal
    so it can be streamed to the client (e.g. Codex) for sandboxed execution.
    Otherwise, executes natively via YOLO tool_dispatcher.
    """
    client_tools = getattr(session, "client_tools", [])
    client_tool_names = {
        t.get("name") or (t.get("function") or {}).get("name")
        for t in client_tools
        if isinstance(t, dict)
    }
    client_tool_names = {name for name in client_tool_names if name}

    clean_name = tool_name
    if clean_name.startswith("mcp__yolo__"):
        clean_name = clean_name[len("mcp__yolo__") :]
    elif clean_name.startswith("yolo__"):
        clean_name = clean_name[len("yolo__") :]

    if tool_name in client_tool_names and not tool_name.startswith("mcp__yolo__"):
        cid = call_id or f"call_{uuid.uuid4().hex[:12]}"
        if signal_handler:
            payload = json.dumps({"call_id": cid, "name": tool_name, "arguments": arguments})
            res = signal_handler(f"YOLO_CLIENT_TOOL:{payload}")
            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                await res
        return "__CLIENT_TOOL_DISPATCHED__"

    # Otherwise fallback to YOLO native execution
    from tool_dispatcher import execute_tool_direct

    is_confirmed = confirmed if confirmed is not None else getattr(session, "yolo_mode", False)
    return await execute_tool_direct(
        tool_name,
        arguments,
        user_id=getattr(session, "user_id", 1),
        signal_handler=signal_handler,
        session=session,
        call_id=call_id,
        confirmed=is_confirmed,
    )


def _extract_responses_input(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract messages from Responses API `input` + `instructions`."""
    messages: List[Dict[str, Any]] = []
    instructions = data.get("instructions")
    if instructions:
        # instructions may be str or list
        text = _get_text_content(instructions) if isinstance(instructions, list) else str(instructions)
        if text.strip():
            messages.append({"role": "system", "content": text.strip()})

    raw_input = data.get("input")
    if raw_input is None:
        # fallback to messages for compat
        raw_input = data.get("messages")
        if raw_input is None:
            return messages

    if isinstance(raw_input, str):
        if raw_input.strip():
            messages.append({"role": "user", "content": raw_input.strip()})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, str):
                if item.strip():
                    messages.append({"role": "user", "content": item.strip()})
            elif isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "function_call":
                    call_id = item.get("call_id") or item.get("id") or ""
                    name = item.get("name", "")
                    arguments = item.get("arguments", "{}")
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    tc = {
                        "id": str(call_id),
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": str(arguments),
                        },
                    }
                    if messages and messages[-1].get("role") == "assistant" and "tool_calls" in messages[-1]:
                        messages[-1]["tool_calls"].append(tc)
                    else:
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tc],
                        })
                    continue

                if item_type == "function_call_output":
                    call_id = item.get("call_id") or item.get("id") or ""
                    out = item.get("output")
                    if out is None:
                        out = ""
                    elif isinstance(out, (dict, list)):
                        out = json.dumps(out)
                    else:
                        out = str(out)
                    messages.append({"role": "tool", "tool_call_id": str(call_id), "content": out})
                    continue

                role = item.get("role", "user")
                content = item.get("content", "")
                # content may be str or list of parts like [{"type":"input_text","text":"..."}]
                if isinstance(content, list):
                    text = _get_text_content(content)
                    # also handle output_text parts
                    if not text:
                        # try to extract from parts with type output_text
                        parts = []
                        for p in content:
                            if isinstance(p, dict) and p.get("type") in {"output_text", "input_text", "text"}:
                                t = p.get("text") or p.get("input_text") or ""
                                if t:
                                    parts.append(str(t))
                        text = " ".join(parts).strip()
                    content = text
                elif content is None:
                    content = ""
                else:
                    content = str(content)
                # For responses, role may be "assistant" with tool calls; keep as is
                messages.append({"role": role, "content": content})
                # If item has type == "message" etc, normalize
            else:
                messages.append({"role": "user", "content": str(item)})
    else:
        messages.append({"role": "user", "content": str(raw_input)})

    return messages


def _openai_error(message: str, status: int = 400) -> web.Response:
    return web.json_response(
        {"error": {"message": message, "type": "invalid_request_error", "code": None}},
        status=status,
    )


# ── Handlers ──

async def handle_list_models(request: web.Request) -> web.Response:
    if not _is_authorized(request):
        return web.json_response({"error": {"message": "Invalid API key", "type": "authentication_error"}}, status=401)
    now = int(time.time())
    def _model_entry(mid: str, disp: str):
        return {
            "id": mid,
            "object": "model",
            "created": now,
            "owned_by": "yolo",
            "slug": mid,
            "display_name": disp,
            "description": f"Yolo agent model {mid}",
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [
                {"effort": "low", "description": "Fast"},
                {"effort": "medium", "description": "Balanced"},
                {"effort": "high", "description": "Deep"},
                {"effort": "ultra", "description": "Ultra Deep Thinking"},
            ],
            "shell_type": "unified_exec",
            "visibility": "hide",
            "supported_in_api": True,
            "priority": 1,
            "additional_speed_tiers": [],
            "service_tiers": [],
            "support_verbosity": True,
            "default_verbosity": "low",
            "apply_patch_tool_type": "freeform",
            "web_search_tool_type": "text_and_image",
            "truncation_policy": {"mode": "auto"},
            "supports_parallel_tool_calls": True,
            "tool_mode": "code_mode_only",
            "multi_agent_version": "v2",
            "context_window": 272000,
            "max_context_window": 872000,
        }
    models = [
        _model_entry("yolo", "Yolo"),
        _model_entry("yolo-think", "Yolo Think"),
        _model_entry("yolo-safe", "Yolo Safe"),
        _model_entry("gpt-5.6-terra", "Yolo Terra (Codex)"),
    ]
    try:
        current = yolo_agent.router.config.model
        if current and current not in {m["id"] for m in models}:
            models.append(_model_entry(current, current))
    except Exception:
        pass
    # Return both OpenAI (data) and Codex (models) shapes
    return web.json_response({"object": "list", "data": models, "models": models})


async def handle_health(request: web.Request) -> web.Response:
    # No auth required for health
    try:
        from monitoring import build_health_payload
        payload = build_health_payload()
    except Exception:
        payload = {"status": "ok"}
    try:
        payload["model"] = yolo_agent.router.config.model
        payload["provider"] = yolo_agent.router.config.provider
    except Exception:
        payload["model"] = os.getenv("MODEL_NAME", "yolo")
    payload["status"] = "ok"
    payload["endpoint"] = "yolo-model-server"
    return web.json_response(payload)


async def handle_chat_completions(request: web.Request) -> web.Response:
    if not _is_authorized(request):
        return web.json_response({"error": {"message": "Invalid API key", "type": "authentication_error"}}, status=401)

    try:
        data = await request.json()
    except Exception:
        return _openai_error("Invalid JSON body")

    model = data.get("model", "yolo")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return _openai_error("`messages` must be a non-empty array")

    stream = bool(data.get("stream", False))
    # tools from caller are ignored in opaque mode unless passthrough enabled
    # (yolo uses its own TOOLS_SCHEMAS)

    api_key = _extract_bearer_token(request)
    user_id = _api_key_to_user_id(api_key)

    # Build ephemeral session
    try:
        session, user_msg = _build_yolo_session(
            user_id=user_id,
            incoming_messages=messages,
            model_name=model,
            client_tools=data.get("tools", []),
        )
        if data.get("tools") or data.get("client_metadata") is not None:
            session.codex_mode = True
    except Exception as e:
        return _openai_error(f"Failed to build session: {e}")

    # Ensure session_manager exists (for memory_service)
    global session_manager
    if session_manager is None:
        try:
            session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
        except Exception:
            from tools.memory_service import get_memory
            # fallback without SessionManager
            class _Fallback:
                memory = get_memory()
            session_manager = _Fallback()  # type: ignore

    memory_service = getattr(session_manager, "memory", None)
    # If session_manager is fallback, try get_memory directly
    if memory_service is None:
        try:
            from tools.memory_service import get_memory
            memory_service = get_memory()
        except Exception:
            memory_service = None

    if stream:
        return await _handle_chat_completions_stream(request, session, user_msg, model, memory_service)
    else:
        return await _handle_chat_completions_non_stream(request, session, user_msg, model, memory_service)


async def _handle_chat_completions_non_stream(
    request: web.Request,
    session: Session,
    user_msg: Any,
    model: str,
    memory_service: Any,
) -> web.Response:
    try:
        final = await yolo_agent.run_agent_turn(
            user_msg, session, signal_handler=None, memory_service=memory_service
        )
    except yolo_agent.PendingConfirmationError as e:
        # In yolo_mode=True this should not happen; if it does, auto-deny and return
        final = f"[Yolo blocked action pending confirmation: {e.action} on {e.path}. Run with yolo mode or approve.]"
    except Exception as exc:
        return web.json_response(
            {"error": {"message": f"Agent error: {exc}", "type": "server_error"}}, status=500
        )

    if not isinstance(final, str):
        final = str(final)

    # Build OpenAI response
    resp_id = f"chatcmpl-yolo-{uuid.uuid4().hex[:8]}"
    now = int(time.time())
    # Token counts from session (accumulated during this ephemeral turn)
    prompt_tokens = getattr(session, "total_prompt_tokens", 0)
    completion_tokens = getattr(session, "total_completion_tokens", 0)
    total_tokens = getattr(session, "total_tokens", prompt_tokens + completion_tokens)

    return web.json_response(
        {
            "id": resp_id,
            "object": "chat.completion",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": final},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
    )


async def _handle_chat_completions_stream(
    request: web.Request,
    session: Session,
    user_msg: Any,
    model: str,
    memory_service: Any,
) -> web.StreamResponse:
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    stream_queue: asyncio.Queue = asyncio.Queue()
    prev_len = 0
    resp_id = f"chatcmpl-yolo-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    async def _signal_handler(signal_text: str):
        nonlocal prev_len
        if signal_text.startswith(yolo_agent.TUIMessage.STREAM + ":"):
            content = signal_text[len(yolo_agent.TUIMessage.STREAM) + 1 :]
            # Emit delta only
            delta = content[prev_len:]
            prev_len = len(content)
            if delta:
                await stream_queue.put(("delta", delta))
        elif signal_text.startswith(yolo_agent.TUIMessage.STREAM + "_END"):
            await stream_queue.put(("end", ""))
        elif signal_text.startswith("__STATUS__:"):
            # ignore status for OpenAI stream
            pass
        elif signal_text.startswith(yolo_agent.TUIMessage.TOOL_CALL + ":"):
            # For opaque mode we hide tool calls; optionally could emit as reasoning
            pass
        elif signal_text.startswith(yolo_agent.TUIMessage.TOOL_RESULT + ":"):
            pass

    async def _run_turn():
        try:
            final = await yolo_agent.run_agent_turn(
                user_msg, session, signal_handler=_signal_handler, memory_service=memory_service
            )
            # Ensure final delta is flushed (in case STREAM didn't cover it)
            if isinstance(final, str) and len(final) > prev_len:
                await stream_queue.put(("delta", final[prev_len:]))
            await stream_queue.put(("done", final))
        except yolo_agent.PendingConfirmationError as e:
            msg = f"[Blocked: {e.action} on {e.path}]"
            if len(msg) > prev_len:
                await stream_queue.put(("delta", msg[prev_len:]))
            await stream_queue.put(("done", msg))
        except Exception as exc:
            await stream_queue.put(("error", str(exc)))

    task = asyncio.create_task(_run_turn())

    try:
        while True:
            try:
                event_type, payload = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                await resp.write(b": keepalive\n\n")
                continue

            if event_type == "delta":
                chunk = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": payload}, "finish_reason": None}],
                }
                await resp.write(f"data: {json.dumps(chunk)}\n\n".encode())
            elif event_type == "done":
                # Final chunk with finish_reason
                final_chunk = {
                    "id": resp_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
                await resp.write(f"data: {json.dumps(final_chunk)}\n\n".encode())
                await resp.write(b"data: [DONE]\n\n")
                break
            elif event_type == "error":
                err_chunk = {"error": {"message": payload, "type": "server_error"}}
                await resp.write(f"data: {json.dumps(err_chunk)}\n\n".encode())
                await resp.write(b"data: [DONE]\n\n")
                break
            elif event_type == "end":
                pass
    except (ConnectionResetError, asyncio.CancelledError):
        task.cancel()
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    return resp


async def handle_anthropic_messages(request: web.Request) -> web.Response:
    """Anthropic-compatible endpoint: POST /v1/messages and POST /v1/messages/count_tokens"""
    if not _is_authorized(request):
        return web.json_response({"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"type": "error", "error": {"type": "invalid_request_error", "message": "Invalid JSON"}}, status=400)

    model = data.get("model", "yolo")
    system = data.get("system", "")
    messages = data.get("messages", [])
    stream = bool(data.get("stream", False))

    # Normalize Anthropic messages to OpenAI shape
    # Anthropic: {"role":"user","content":[{"type":"text","text":"..."}]} or str
    openai_messages: List[Dict[str, Any]] = []
    if system:
        # system may be str or list
        system_text = _get_text_content(system) if isinstance(system, list) else str(system)
        if system_text:
            openai_messages.append({"role": "system", "content": system_text})

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            text = _get_text_content(content)
            # Preserve tool_use/tool_result as text for opaque mode
            # If content contains tool_use, flatten to text
            # For now, join text parts
            content = text
        openai_messages.append({"role": role, "content": str(content) if content is not None else ""})

    if not openai_messages:
        return web.json_response({"type": "error", "error": {"type": "invalid_request_error", "message": "`messages` required"}}, status=400)

    api_key = _extract_bearer_token(request)
    user_id = _api_key_to_user_id(api_key)

    try:
        session, user_msg = _build_yolo_session(user_id=user_id, incoming_messages=openai_messages, model_name=model)
    except Exception as e:
        return web.json_response({"type": "error", "error": {"type": "invalid_request_error", "message": str(e)}}, status=400)

    global session_manager
    if session_manager is None:
        try:
            session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
        except Exception:
            from tools.memory_service import get_memory
            class _Fallback:
                memory = get_memory()
            session_manager = _Fallback()  # type: ignore
    memory_service = getattr(session_manager, "memory", None)
    if memory_service is None:
        try:
            from tools.memory_service import get_memory
            memory_service = get_memory()
        except Exception:
            memory_service = None

    if stream:
        # Stream in Anthropic SSE format: event: content_block_delta
        return await _handle_anthropic_stream(request, session, user_msg, model, memory_service)
    else:
        try:
            final = await yolo_agent.run_agent_turn(user_msg, session, signal_handler=None, memory_service=memory_service)
        except yolo_agent.PendingConfirmationError as e:
            final = f"[Blocked: {e.action} on {e.path}]"
        except Exception as exc:
            return web.json_response({"type": "error", "error": {"type": "api_error", "message": str(exc)}}, status=500)

        if not isinstance(final, str):
            final = str(final)

        # Anthropic response shape
        msg_id = f"msg_yolo_{uuid.uuid4().hex[:8]}"
        prompt_tokens = getattr(session, "total_prompt_tokens", 0)
        completion_tokens = getattr(session, "total_completion_tokens", 0)
        return web.json_response(
            {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": final}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": prompt_tokens, "output_tokens": completion_tokens},
            }
        )


async def _handle_anthropic_stream(
    request: web.Request,
    session: Session,
    user_msg: Any,
    model: str,
    memory_service: Any,
) -> web.StreamResponse:
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    stream_queue: asyncio.Queue = asyncio.Queue()
    prev_len = 0
    msg_id = f"msg_yolo_{uuid.uuid4().hex[:8]}"

    async def _signal_handler(signal_text: str):
        nonlocal prev_len
        if signal_text.startswith(yolo_agent.TUIMessage.STREAM + ":"):
            content = signal_text[len(yolo_agent.TUIMessage.STREAM) + 1 :]
            delta = content[prev_len:]
            prev_len = len(content)
            if delta:
                await stream_queue.put(("delta", delta))

    async def _run_turn():
        try:
            final = await yolo_agent.run_agent_turn(user_msg, session, signal_handler=_signal_handler, memory_service=memory_service)
            if isinstance(final, str) and len(final) > prev_len:
                await stream_queue.put(("delta", final[prev_len:]))
            await stream_queue.put(("done", final))
        except yolo_agent.PendingConfirmationError as e:
            msg = f"[Blocked: {e.action} on {e.path}]"
            if len(msg) > prev_len:
                await stream_queue.put(("delta", msg[prev_len:]))
            await stream_queue.put(("done", msg))
        except Exception as exc:
            await stream_queue.put(("error", str(exc)))

    task = asyncio.create_task(_run_turn())

    # Send Anthropic stream preamble
    await resp.write(f"event: message_start\ndata: {json.dumps({'type':'message_start','message':{'id':msg_id,'type':'message','role':'assistant','content':[],'model':model}})}\n\n".encode())
    await resp.write(f"event: content_block_start\ndata: {json.dumps({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}})}\n\n".encode())

    try:
        while True:
            try:
                event_type, payload = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                await resp.write(b": keepalive\n\n")
                continue

            if event_type == "delta":
                delta_evt = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": payload}}
                await resp.write(f"event: content_block_delta\ndata: {json.dumps(delta_evt)}\n\n".encode())
            elif event_type == "done":
                await resp.write(f"event: content_block_stop\ndata: {json.dumps({'type':'content_block_stop','index':0})}\n\n".encode())
                await resp.write(f"event: message_delta\ndata: {json.dumps({'type':'message_delta','delta':{'stop_reason':'end_turn','stop_sequence':None}})}\n\n".encode())
                await resp.write(f"event: message_stop\ndata: {json.dumps({'type':'message_stop'})}\n\n".encode())
                break
            elif event_type == "error":
                await resp.write(f"event: error\ndata: {json.dumps({'type':'error','error':{'type':'api_error','message':payload}})}\n\n".encode())
                break
    except (ConnectionResetError, asyncio.CancelledError):
        task.cancel()
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    return resp


async def handle_responses(request: web.Request) -> web.Response:
    """OpenAI Responses API: POST /v1/responses (for Codex wire_api=responses)."""
    if not _is_authorized(request):
        return web.json_response({"error": {"message": "Invalid API key", "type": "invalid_request_error"}}, status=401)

    try:
        data = await request.json()
    except Exception:
        return _openai_error("Invalid JSON body")

    model = data.get("model", "yolo")
    stream = bool(data.get("stream", False))
    # Extract messages from Responses input
    openai_messages = _extract_responses_input(data)
    if not openai_messages:
        # If input empty, try fallback to prompt
        prompt = data.get("prompt") or data.get("input_text") or ""
        if prompt:
            openai_messages = [{"role": "user", "content": str(prompt)}]
        else:
            return _openai_error("`input` must be a non-empty string or array")

    api_key = _extract_bearer_token(request)
    user_id = _api_key_to_user_id(api_key)

    try:
        raw_tools = data.get("tools", [])
        session, user_msg = _build_yolo_session(
            user_id=user_id,
            incoming_messages=openai_messages,
            model_name=model,
            client_tools=raw_tools,
        )
        # In Responses API (wire_api=responses), session operates in codex_mode
        session.codex_mode = True
    except Exception as e:
        return _openai_error(f"Failed to build session: {e}")

    global session_manager
    if session_manager is None:
        try:
            session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
        except Exception:
            from tools.memory_service import get_memory
            class _Fallback:
                memory = get_memory()
            session_manager = _Fallback()  # type: ignore
    memory_service = getattr(session_manager, "memory", None)
    if memory_service is None:
        try:
            from tools.memory_service import get_memory
            memory_service = get_memory()
        except Exception:
            memory_service = None

    if stream:
        return await _handle_responses_stream(request, session, user_msg, model, memory_service)
    else:
        try:
            final = await yolo_agent.run_agent_turn(user_msg, session, signal_handler=None, memory_service=memory_service)
        except yolo_agent.PendingConfirmationError as e:
            final = f"[Blocked: {e.action} on {e.path}]"
        except Exception as exc:
            return web.json_response({"error": {"message": f"Agent error: {exc}", "type": "server_error"}}, status=500)

        if not isinstance(final, str):
            final = str(final)

        resp_id = f"resp_yolo_{uuid.uuid4().hex[:12]}"
        created_at = int(time.time())
        prompt_tokens = getattr(session, "total_prompt_tokens", 0)
        completion_tokens = getattr(session, "total_completion_tokens", 0)
        total_tokens = getattr(session, "total_tokens", prompt_tokens + completion_tokens)

        # Responses API object
        return web.json_response(
            {
                "id": resp_id,
                "object": "response",
                "created_at": created_at,
                "model": model,
                "output": [
                    {
                        "id": f"msg_{uuid.uuid4().hex[:8]}",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": final}],
                    }
                ],
                "status": "completed",
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            }
        )


def _format_tool_commentary(name: str, args: Any, result: Optional[str] = None) -> str:
    """Format an internal tool execution into clean human-readable commentary for Codex Desktop."""
    clean_name = name
    if clean_name.startswith("mcp__yolo__"):
        clean_name = clean_name[len("mcp__yolo__") :]
    elif clean_name.startswith("yolo__"):
        clean_name = clean_name[len("yolo__") :]
    elif clean_name.startswith("mcp__"):
        parts = clean_name.split("__", 2)
        if len(parts) == 3 and parts[1] == "yolo":
            clean_name = parts[2]

    summary = ""
    if isinstance(args, dict):
        if clean_name in ("read_file", "view_file") and "path" in args:
            summary = f"📖 Read file `{args['path']}`"
        elif clean_name in ("list_dir", "list_directory") and "path" in args:
            summary = f"📁 Listed directory `{args['path']}`"
        elif clean_name in ("write_file", "write_to_file") and "path" in args:
            summary = f"✏️ Wrote to `{args['path']}`"
        elif clean_name in ("replace_file_content", "edit_file") and "path" in args:
            summary = f"✏️ Modified `{args['path']}`"
        elif clean_name in ("web_search", "search_web") and "query" in args:
            summary = f"🌐 Searched web: \"{args['query']}\""
        elif clean_name in ("read_url_content", "fetch_web_page") and "url" in args:
            summary = f"🌐 Fetched URL: `{args['url']}`"
        elif clean_name in ("exec_command", "run_command"):
            cmd = args.get("cmd") or args.get("command") or ""
            summary = f"⚡ Ran command: `{cmd}`"
        elif clean_name in ("read_user_identity", "user_identity"):
            summary = "👤 Checked user identity"
        elif clean_name in ("memory_search", "search_memory") and "query" in args:
            summary = f"🧠 Searched memory: \"{args['query']}\""
        else:
            arg_items = [f"{k}={repr(v)}" for k, v in args.items()]
            arg_str = ", ".join(arg_items)
            if len(arg_str) > 100:
                arg_str = arg_str[:97] + "..."
            summary = f"🔧 `{clean_name}({arg_str})`"
    elif args:
        summary = f"🔧 `{clean_name}({args})`"
    else:
        summary = f"🔧 `{clean_name}()`"

    if result and isinstance(result, str):
        res_str = result.strip()
        if res_str.lower().startswith("error") or "traceback" in res_str.lower():
            err_line = res_str.split("\n")[0]
            if len(err_line) > 120:
                err_line = err_line[:117] + "..."
            summary += f"\n⚠️ {err_line}"

    return summary


async def _handle_responses_stream(
    request: web.Request,
    session: Session,
    user_msg: Any,
    model: str,
    memory_service: Any,
) -> web.StreamResponse:
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)

    stream_queue: asyncio.Queue = asyncio.Queue()
    prev_len = 0
    resp_id = f"resp_yolo_{uuid.uuid4().hex[:12]}"
    created_at = int(time.time())

    async def _signal_handler(signal_text: str):
        nonlocal prev_len
        if signal_text.startswith(yolo_agent.TUIMessage.STREAM + ":"):
            content = signal_text[len(yolo_agent.TUIMessage.STREAM) + 1 :]
            delta = content[prev_len:]
            prev_len = len(content)
            if delta:
                await stream_queue.put(("delta", delta))
        elif signal_text.startswith("YOLO_CLIENT_TOOL:"):
            try:
                tool_info = json.loads(signal_text[len("YOLO_CLIENT_TOOL:") :])
                if not isinstance(tool_info, dict):
                    tool_info = {}
            except Exception:
                tool_info = {}
            await stream_queue.put(("function_call", tool_info))
        elif signal_text.startswith("__TOOL_CALL__:"):
            try:
                call_info = json.loads(signal_text[len("__TOOL_CALL__:") :])
                if isinstance(call_info, dict):
                    await stream_queue.put(("tool_call", call_info))
            except Exception:
                pass
        elif signal_text.startswith("__TOOL_RESULT__:"):
            try:
                res_info = json.loads(signal_text[len("__TOOL_RESULT__:") :])
                if isinstance(res_info, dict):
                    await stream_queue.put(("tool_result", res_info))
            except Exception:
                pass

    async def _run_turn():
        try:
            final = await yolo_agent.run_agent_turn(user_msg, session, signal_handler=_signal_handler, memory_service=memory_service)
            if final == "__CLIENT_TOOL_DISPATCHED__":
                # function_call was already queued via YOLO_CLIENT_TOOL signal;
                # don't emit text output — stream loop handles it.
                return
            if isinstance(final, str) and len(final) > prev_len:
                await stream_queue.put(("delta", final[prev_len:]))
            await stream_queue.put(("done", final))
        except yolo_agent.PendingConfirmationError as e:
            msg = f"[Blocked: {e.action} on {e.path}]"
            if len(msg) > prev_len:
                await stream_queue.put(("delta", msg[prev_len:]))
            await stream_queue.put(("done", msg))
        except Exception as exc:
            await stream_queue.put(("error", str(exc)))

    task = asyncio.create_task(_run_turn())

    # Initial created event
    await resp.write(f"event: response.created\ndata: {json.dumps({'type':'response.created','response':{'id':resp_id,'object':'response','status':'in_progress','model':model,'created_at':created_at}})}\n\n".encode())
    await resp.write(f"event: response.in_progress\ndata: {json.dumps({'type':'response.in_progress','response':{'id':resp_id}})}\n\n".encode())

    curr_output_index = 0
    completed_output_items: List[Dict[str, Any]] = []
    active_tool_calls: Dict[str, Dict[str, Any]] = {}
    final_item_id = f"msg_{uuid.uuid4().hex[:8]}"
    msg_item_started = False

    async def _ensure_msg_item_started():
        nonlocal msg_item_started
        if not msg_item_started:
            item = {
                "id": final_item_id,
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "status": "in_progress",
                "content": [],
            }
            await resp.write(
                f"event: response.output_item.added\ndata: {json.dumps({'type':'response.output_item.added','output_index':curr_output_index,'item':item})}\n\n".encode()
            )
            await resp.write(
                f"event: response.content_part.added\ndata: {json.dumps({'type':'response.content_part.added','output_index':curr_output_index,'content_index':0,'item_id':final_item_id,'part':{'type':'output_text','text':''}})}\n\n".encode()
            )
            msg_item_started = True

    try:
        while True:
            try:
                event_type, payload = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                await resp.write(b": keepalive\n\n")
                continue

            if event_type == "tool_call":
                if isinstance(payload, dict):
                    call_id = payload.get("call_id", "")
                    if call_id:
                        active_tool_calls[call_id] = payload
                    else:
                        active_tool_calls[f"_tmp_{uuid.uuid4().hex[:6]}"] = payload

            elif event_type == "tool_result":
                if not isinstance(payload, dict):
                    payload = {}
                call_id = payload.get("call_id", "")
                call_info = active_tool_calls.pop(call_id, {})
                func_name = payload.get("name") or call_info.get("name", "tool")
                func_args = call_info.get("args") or payload.get("args", {})
                func_result = payload.get("result", "")

                summary_text = _format_tool_commentary(func_name, func_args, func_result)
                item_id = f"msg_tool_{uuid.uuid4().hex[:8]}"
                tool_item = {
                    "id": item_id,
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "status": "in_progress",
                    "content": [],
                }
                await resp.write(f"event: response.output_item.added\ndata: {json.dumps({'type':'response.output_item.added','output_index':curr_output_index,'item':tool_item})}\n\n".encode())
                await resp.write(f"event: response.content_part.added\ndata: {json.dumps({'type':'response.content_part.added','output_index':curr_output_index,'content_index':0,'item_id':item_id,'part':{'type':'output_text','text':''}})}\n\n".encode())
                await resp.write(f"event: response.output_text.delta\ndata: {json.dumps({'type':'response.output_text.delta','output_index':curr_output_index,'content_index':0,'item_id':item_id,'delta':summary_text})}\n\n".encode())
                await resp.write(f"event: response.output_text.done\ndata: {json.dumps({'type':'response.output_text.done','output_index':curr_output_index,'content_index':0,'item_id':item_id,'text':summary_text})}\n\n".encode())
                await resp.write(f"event: response.content_part.done\ndata: {json.dumps({'type':'response.content_part.done','output_index':curr_output_index,'content_index':0,'item_id':item_id,'part':{'type':'output_text','text':summary_text}})}\n\n".encode())
                tool_item["status"] = "completed"
                tool_item["content"] = [{"type": "output_text", "text": summary_text}]
                await resp.write(f"event: response.output_item.done\ndata: {json.dumps({'type':'response.output_item.done','output_index':curr_output_index,'item':tool_item})}\n\n".encode())

                completed_output_items.append(tool_item)
                curr_output_index += 1

            elif event_type == "function_call":
                if not isinstance(payload, dict):
                    payload = {}
                call_id = payload.get("call_id", f"call_{uuid.uuid4().hex[:8]}")
                name = payload.get("name", "exec_command")
                args = payload.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)

                item = {
                    "id": call_id,
                    "type": "function_call",
                    "name": name,
                    "call_id": call_id,
                    "status": "in_progress",
                    "arguments": "",
                }
                await resp.write(f"event: response.output_item.added\ndata: {json.dumps({'type':'response.output_item.added','output_index':curr_output_index,'item':item})}\n\n".encode())
                await resp.write(f"event: response.function_call_arguments.delta\ndata: {json.dumps({'type':'response.function_call_arguments.delta','output_index':curr_output_index,'item_id':call_id,'call_id':call_id,'delta':args_str})}\n\n".encode())
                await resp.write(f"event: response.function_call_arguments.done\ndata: {json.dumps({'type':'response.function_call_arguments.done','output_index':curr_output_index,'item_id':call_id,'call_id':call_id,'arguments':args_str})}\n\n".encode())
                item["status"] = "completed"
                item["arguments"] = args_str
                await resp.write(f"event: response.output_item.done\ndata: {json.dumps({'type':'response.output_item.done','output_index':curr_output_index,'item':item})}\n\n".encode())

                completed_output_items.append(item)
                # Complete response for this tool dispatch turn
                completed = {
                    "type": "response.completed",
                    "response": {
                        "id": resp_id,
                        "object": "response",
                        "status": "completed",
                        "model": model,
                        "output": completed_output_items,
                    },
                }
                await resp.write(f"event: response.completed\ndata: {json.dumps(completed)}\n\n".encode())
                break
            elif event_type == "delta":
                await _ensure_msg_item_started()
                evt = {"type": "response.output_text.delta", "delta": payload, "output_index": curr_output_index, "content_index": 0, "item_id": final_item_id}
                await resp.write(f"event: response.output_text.delta\ndata: {json.dumps(evt)}\n\n".encode())
            elif event_type == "done":
                await _ensure_msg_item_started()
                final_text = payload or ""
                await resp.write(f"event: response.output_text.done\ndata: {json.dumps({'type':'response.output_text.done','output_index':curr_output_index,'content_index':0,'item_id':final_item_id,'text':final_text})}\n\n".encode())
                await resp.write(f"event: response.content_part.done\ndata: {json.dumps({'type':'response.content_part.done','output_index':curr_output_index,'content_index':0,'item_id':final_item_id,'part':{'type':'output_text','text':final_text}})}\n\n".encode())
                final_item = {
                    "id": final_item_id,
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": final_text}],
                }
                await resp.write(f"event: response.output_item.done\ndata: {json.dumps({'type':'response.output_item.done','output_index':curr_output_index,'item':final_item})}\n\n".encode())
                completed_output_items.append(final_item)
                completed = {
                    "type": "response.completed",
                    "response": {
                        "id": resp_id,
                        "object": "response",
                        "status": "completed",
                        "model": model,
                        "output": completed_output_items,
                    },
                }
                await resp.write(f"event: response.completed\ndata: {json.dumps(completed)}\n\n".encode())
                break
            elif event_type == "error":
                await resp.write(f"event: error\ndata: {json.dumps({'type':'error','error':{'message':payload}})}\n\n".encode())
                break
    except (ConnectionResetError, asyncio.CancelledError):
        task.cancel()
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    return resp


# ── App builder ──

def create_app() -> web.Application:
    app = web.Application(client_max_size=1024**2 * 20)  # 20MB for large prompts
    # OpenAI compat
    app.router.add_get("/v1/models", handle_list_models)
    app.router.add_get("/models", handle_list_models)  # alias
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_post("/chat/completions", handle_chat_completions)  # alias without /v1
    # OpenAI Responses API (Codex wire_api=responses)
    app.router.add_post("/v1/responses", handle_responses)
    app.router.add_post("/responses", handle_responses)  # alias
    # Anthropic compat
    app.router.add_post("/v1/messages", handle_anthropic_messages)
    app.router.add_post("/v1/messages/count_tokens", handle_anthropic_messages)  # reuse
    # Health
    app.router.add_get("/health", handle_health)
    app.router.add_get("/v1/health", handle_health)
    app.router.add_get("/", handle_health)
    return app


def init_session_manager(shared_manager: Optional[SessionManager] = None):
    global session_manager
    if shared_manager is not None:
        session_manager = shared_manager
    elif session_manager is None:
        try:
            session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
        except Exception as e:
            print(f"[yolo-model] SessionManager init failed: {e}", file=sys.stderr)
            session_manager = None
    return session_manager


async def run_yolo_model_server(
    host: str = YOLO_MODEL_HOST,
    port: int = YOLO_MODEL_PORT,
    shared_session_manager: Optional[SessionManager] = None,
) -> None:
    """Start the Yolo model server (for use from server.py)."""
    init_session_manager(shared_session_manager)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[yolo-model] Listening on http://{host}:{port}")
    print(f"[yolo-model] OpenAI compat: http://{host}:{port}/v1/chat/completions")
    print(f"[yolo-model] Responses API: http://{host}:{port}/v1/responses")
    print(f"[yolo-model] Anthropic compat: http://{host}:{port}/v1/messages")
    print(f"[yolo-model] Models: http://{host}:{port}/v1/models")
    sys.stdout.flush()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()
        raise


def main():
    init_session_manager()
    app = create_app()
    print(f"[yolo-model] Starting on http://{YOLO_MODEL_HOST}:{YOLO_MODEL_PORT}")
    try:
        model = yolo_agent.router.config.model
        provider = yolo_agent.router.config.provider
        print(f"[yolo-model] Yolo agent model: {model} via {provider}")
    except Exception:
        print(f"[yolo-model] Yolo agent model: yolo (agent loop)")
    print("[yolo-model] Auth:", "DISABLED" if YOLO_MODEL_DISABLE_AUTH else f"enabled (keys: {len(_get_allowed_keys())})")
    sys.stdout.flush()
    try:
        web.run_app(app, host=YOLO_MODEL_HOST, port=YOLO_MODEL_PORT, print=None)
    except OSError as e:
        if getattr(e, "errno", None) == 98:
            print(f"[yolo-model] Port {YOLO_MODEL_PORT} in use.")
        else:
            raise


if __name__ == "__main__":
    main()
