#!/usr/bin/env python3
"""Lightweight HTTP API bridge for the Yolo Desktop app.

This bridge is a thin gateway — just like bot.py (Telegram) or discord_gateway.py.
It reuses the SAME SessionManager → SQLite → Mem0 stack, so Desktop and Telegram
share conversation history, mode flags, pending confirmations, and long-term memory.

Architecture:
  Telegram  ─┐
  Discord   ─┤── SessionManager ── SQLite (~/.yolo/yolo_v2.db)
  CLI       ─┤                  └─ Mem0/Qdrant (long-term memory)
  Desktop   ─┘
"""

import asyncio
import base64
import binascii
import hmac
import json
import secrets
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure the project root is on the path so we can import agent/session/tools.
# When imported from server.py, the CWD is already correct.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.settings import load_settings

load_settings()

from aiohttp import web  # noqa: E402

import agent as yolo_agent  # noqa: E402
from session import SessionManager  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
import mimetypes  # noqa: E402

# ── Shared state (same as bot.py) ──
TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
session_manager: SessionManager = None  # type: ignore
BRIDGE_AUTH_DISABLED = os.getenv("DESKTOP_BRIDGE_DISABLE_AUTH", "false").lower() == "true"

def get_bridge_token() -> str:
    """Retrieve the bridge token from environment or a persistent file."""
    # 1. Environment variable (highest priority)
    env_token = os.getenv("DESKTOP_BRIDGE_TOKEN")
    if env_token:
        return env_token

    # 2. Persistent file (~/.yolo/.bridge_token)
    yolo_home = Path(os.getenv("YOLO_HOME", str(Path.home() / ".yolo"))).expanduser().resolve()
    token_file = yolo_home / ".bridge_token"
    
    if token_file.exists():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # 3. Generate new and persist
    new_token = secrets.token_urlsafe(32)
    try:
        yolo_home.mkdir(parents=True, exist_ok=True)
        token_file.write_text(new_token, encoding="utf-8")
        # Ensure file is only readable by the user
        token_file.chmod(0o600)
    except Exception as e:
        print(f"[desktop-bridge] Warning: Could not persist bridge token: {e}")
    
    return new_token

BRIDGE_TOKEN = get_bridge_token()
ALLOWED_ORIGINS = {
    "null",
    f"http://127.0.0.1:{os.getenv('DESKTOP_BRIDGE_PORT', '8790')}",
    f"http://localhost:{os.getenv('DESKTOP_BRIDGE_PORT', '8790')}",
}
ALLOWED_ORIGINS.update(
    origin.strip()
    for origin in os.getenv("DESKTOP_BRIDGE_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)

# Use the same user ID as Telegram so sessions/memories are shared.
_allowed = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
DEFAULT_USER_ID = int(_allowed.split(",")[0].strip()) if _allowed.strip() else 1


@web.middleware
async def bridge_security_middleware(request: web.Request, handler):
    if BRIDGE_AUTH_DISABLED:
        return await handler(request)

    if request.path.startswith(("/artifacts/", "/uploads/")):
        return await handler(request)

    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return web.json_response({"error": "Origin not allowed"}, status=403)

    token = request.headers.get("X-Yolo-Bridge-Token", "")
    if request.path == "/health" and not token:
        return await handler(request)
    if not hmac.compare_digest(token, BRIDGE_TOKEN):
        return web.json_response({"error": "Unauthorized"}, status=401)

    return await handler(request)


def get_uploads_dir() -> Path:
    from tools.base import YOLO_ARTIFACTS
    uploads_dir = Path(YOLO_ARTIFACTS) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir


def safe_upload_filename(name: str, fallback: str = "upload.bin") -> str:
    base = Path(str(name or fallback)).name
    cleaned = "".join(c for c in base if c.isalnum() or c in {"-", "_", "."})
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def resolve_upload_path(name: str) -> Path:
    uploads_dir = get_uploads_dir().resolve()
    file_path = (uploads_dir / safe_upload_filename(name)).resolve(strict=False)
    try:
        file_path.relative_to(uploads_dir)
    except ValueError as exc:
        raise ValueError("Attachment path escapes uploads directory") from exc
    return file_path


def decode_data_url_payload(data: str) -> bytes:
    payload = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    try:
        return base64.b64decode(payload, validate=True)
    except binascii.Error:
        return base64.b64decode(payload)


# ── HTTP Handlers ──



async def prepare_user_message(text: str, attachments: list) -> Any:
    """
    Prepare a user message, prioritizing native multi-modal support.
    Fallback OCR/Transcription pipelines have been removed.
    """
    from llm_router import load_llm_config
    config = load_llm_config()
    
    native_vision = config.supports_vision()
    native_audio = config.supports_audio()
    native_docs = config.supports_documents()
    
    parts = []
    if text:
        parts.append({"type": "text", "text": text})
    
    attachments_text = ""

    for att in attachments:
        original_name = str(att.get("name", "unnamed"))
        name = safe_upload_filename(original_name)
        data = att.get("content", "")
        mime_type = att.get("type")
        
        if not mime_type or mime_type in ["application/octet-stream", "text/plain"]:
            guessed, _ = mimetypes.guess_type(name)
            if guessed:
                mime_type = guessed
            else:
                mime_type = mime_type or "text/plain"

        # Save the file to disk so the agent can use tools on it
        file_path = resolve_upload_path(name)
        try:
            if data.startswith("data:") and ";base64," in data:
                with open(file_path, "wb") as f:
                    f.write(decode_data_url_payload(data))
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(data)
            attachments_text += f"\n- File Attached: `{name}` (Saved to disk at `{file_path}`)\n"
        except Exception as e:
            attachments_text += f"\n- Error saving `{original_name}` to disk: {e}\n"

        if mime_type.startswith("image/"):
            if native_vision:
                b64 = data.split(",")[1] if "," in data else data
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"}
                })
            else:
                attachments_text += f"  [Omitted Image Data: Native vision not supported by current model. Use tools to analyze `{file_path}`]\n"
        
        elif mime_type.startswith("audio/"):
            if native_audio:
                b64 = data.split(",")[1] if "," in data else data
                parts.append({
                    "type": "input_audio",
                    "input_audio": {"data": b64, "format": mime_type.split("/")[1]}
                })
            else:
                attachments_text += f"  [Omitted Audio Data: Native audio not supported by current model. Use tools to analyze `{file_path}`]\n"
        
        else:
            # Binary or text file
            if mime_type == "application/pdf" and native_docs:
                b64 = data.split(",")[1] if "," in data else data
                # Format varies by provider; using the most common structure for LiteLLM/Anthropic/Gemini
                if config.provider == "anthropic":
                    parts.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64
                        }
                    })
                else:
                    # General multimodal part format
                    parts.append({
                        "type": "file",
                        "data": b64,
                        "mime_type": "application/pdf"
                    })
                attachments_text += f"  [Sent PDF natively to model for direct analysis. Use tools only if you need deeper file manipulation.]\n"
                continue

            suffix = file_path.suffix.lower()
            if suffix in (".pdf", ".docx", ".pptx", ".xlsx", ".md"):
                try:
                    from tools.document_parser import extract_text_from_file
                    parsed_text = extract_text_from_file(file_path)
                    attachments_text += f"  Parsed Document Content:\n{parsed_text}\n"
                except Exception as e:
                    attachments_text += f"  [Error parsing document: {e}]\n"
                continue

            if data.startswith("data:") and ";base64," in data and not mime_type.startswith("text/"):
                attachments_text += f"  [Omitted Binary Data: {mime_type}. Use tools (e.g. read_file, python scripts) to analyze `{file_path}`]\n"
                continue
                
            MAX_TEXT_ATTACHMENT = 50000 
            if len(data) > MAX_TEXT_ATTACHMENT:
                truncated = data[:MAX_TEXT_ATTACHMENT] + "\n... [TRUNCATED] ..."
                attachments_text += f"  Inline Content Preview (Truncated):\n{truncated}\n"
            else:
                attachments_text += f"  Inline Content:\n{data}\n"

    if attachments_text:
        found = False
        header = "\n\n**[File Attachments]**\n"
        for p in parts:
            if p["type"] == "text":
                p["text"] += header + attachments_text
                found = True
                break
        if not found:
            parts.append({"type": "text", "text": header + attachments_text})

    if len(parts) == 1 and parts[0]["type"] == "text":
        return parts[0]["text"]
    
    return parts



async def handle_chat(request: web.Request) -> web.Response:
    """POST /chat  — send a user message through the shared session."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message = data.get("message", "").strip()
    user_id = int(data.get("user_id", 1))
    attachments = data.get("attachments", [])

    if not message and not attachments:
        return web.json_response({"error": "Empty message"}, status=400)

    # Use the SAME session that Telegram/CLI would use for this user_id.
    # SessionManager.get_or_create() loads from SQLite if not in memory.
    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        
        user_msg = await prepare_user_message(message, attachments)

        try:
            response = await yolo_agent.run_agent_turn(
                user_msg,
                session,
                signal_handler=None,
                memory_service=session_manager.memory,
            )
            session_manager.save(user_id)
            return web.json_response({"response": response})
        except yolo_agent.PendingConfirmationError as e:
            # Phase 2: Native HITL UI — Return needs_confirmation instead of auto-approving.
            return web.json_response({
                "status": "needs_confirmation",
                "action": e.action,
                "tool_args": e.tool_args,
                "tool_call_id": e.tool_call_id,
                "user_id": user_id
            })
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)


async def handle_chat_stream(request: web.Request) -> web.StreamResponse:
    """POST /chat/stream — SSE streaming: tokens arrive as `data:` events."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message = data.get("message", "").strip()
    user_id = int(data.get("user_id", 1))
    attachments = data.get("attachments", [])

    if not message and not attachments:
        return web.json_response({"error": "Empty message"}, status=400)

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

    stream_queue = asyncio.Queue()

    async def _signal_handler(signal_text: str):
        """Bridge agent signals into the SSE queue."""
        if signal_text.startswith("__STREAM__:"):
            content = signal_text[len("__STREAM__:"):]
            await stream_queue.put(("stream", content))
        elif signal_text.startswith("__STREAM_END__"):
            await stream_queue.put(("end", ""))
        elif signal_text.startswith("__STATUS__:"):
            status_text = signal_text[len("__STATUS__:"):].strip()
            if status_text:
                await stream_queue.put(("status", status_text))
        elif signal_text.startswith("__TOOL_CALL__:"):
            try:
                data = json.loads(signal_text[len("__TOOL_CALL__:"):])
                await stream_queue.put(("tool_call", data))
            except Exception:
                pass
        elif signal_text.startswith("__TOOL_RESULT__:"):
            try:
                data = json.loads(signal_text[len("__TOOL_RESULT__:"):])
                await stream_queue.put(("tool_result", data))
            except Exception:
                pass
        elif signal_text.startswith("__SEND_FILE__:"):
            file_path = signal_text[len("__SEND_FILE__:"):].strip()
            from tools.base import YOLO_ARTIFACTS
            abs_path = os.path.abspath(file_path)
            
            try:
                rel_to_artifacts = os.path.relpath(abs_path, YOLO_ARTIFACTS)
                if not rel_to_artifacts.startswith(".."):
                    # Use a stable URL prefix
                    url = f"/artifacts/{rel_to_artifacts}"
                else:
                    url = f"file://{abs_path}"
            except Exception:
                url = f"file://{abs_path}"
                
            is_image = any(abs_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"])
            await stream_queue.put(("artifact", {
                "url": url, 
                "type": "image" if is_image else "file", 
                "name": os.path.basename(abs_path)
            }))

    async def _run_turn():
        """Run the agent turn in background and push final result."""
        try:
            async with session_manager.get_lock(user_id):
                session = session_manager.get_or_create(user_id)
                
                user_msg = await prepare_user_message(message, attachments)

                try:
                    final = await yolo_agent.run_agent_turn(
                        user_msg,
                        session,
                        signal_handler=_signal_handler,
                        memory_service=session_manager.memory,
                    )
                    session_manager.save(user_id)
                    await stream_queue.put(("done", final))
                except yolo_agent.PendingConfirmationError as e:
                    # Phase 2: Native HITL UI
                    await stream_queue.put(("needs_confirmation", {
                        "action": e.action,
                        "tool_args": e.tool_args,
                        "tool_call_id": e.tool_call_id,
                        "user_id": user_id
                    }))
        except Exception as exc:
            await stream_queue.put(("error", str(exc)))

    task = asyncio.create_task(_run_turn())

    try:
        while True:
            try:
                event_type, payload = await asyncio.wait_for(stream_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                # Send SSE comment to prevent proxy/browser idle timeouts during long tool runs
                await resp.write(b": keepalive\n\n")
                continue

            if event_type == "stream":
                await resp.write(f"event: stream\ndata: {json.dumps(payload)}\n\n".encode())
            elif event_type == "status":
                await resp.write(f"event: status\ndata: {json.dumps(payload)}\n\n".encode())
            elif event_type == "tool_call":
                await resp.write(f"event: tool_call\ndata: {json.dumps(payload)}\n\n".encode())
            elif event_type == "tool_result":
                await resp.write(f"event: tool_result\ndata: {json.dumps(payload)}\n\n".encode())
            elif event_type == "artifact":
                await resp.write(f"event: artifact\ndata: {json.dumps(payload)}\n\n".encode())
            elif event_type == "needs_confirmation":
                await resp.write(f"event: needs_confirmation\ndata: {json.dumps(payload)}\n\n".encode())
                break
            elif event_type == "done":
                await resp.write(f"event: done\ndata: {json.dumps(payload)}\n\n".encode())
                break
            elif event_type == "error":
                await resp.write(f"event: error\ndata: {json.dumps(payload)}\n\n".encode())
                break
            elif event_type == "end":
                pass  # Stream ended, wait for done
    except (ConnectionResetError, asyncio.CancelledError):
        task.cancel()
    finally:
        if not task.done():
            await task

    return resp


async def handle_confirm(request: web.Request) -> web.Response:
    """POST /confirm — Resolve a pending confirmation."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    user_id = int(data.get("user_id", 1))
    confirmed = data.get("confirmed", False)
    
    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        
        if not session.pending_confirmations:
            return web.json_response({"error": "No pending confirmations"}, status=400)
            
        try:
            if confirmed:
                # We currently only support single-confirm via the desktop UI
                response = await yolo_agent.resolve_confirmations(
                    session, user_id, signal_handler=None, confirm_all=False
                )
            else:
                await yolo_agent.deny_confirmations(session, deny_all=False)
                # Re-run the turn to get the final response
                response = await yolo_agent.run_agent_turn(
                    None, session, signal_handler=None, memory_service=session_manager.memory
                )
                
            session_manager.save(user_id)
            return web.json_response({"response": response})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)


async def handle_command(request: web.Request) -> web.Response:
    """POST /command  — execute a slash command against the shared session."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    cmd = data.get("command", "").strip().lower()
    args = data.get("args", [])
    user_id = int(data.get("user_id", 1))

    async with session_manager.get_lock(user_id):
        session = session_manager.get_or_create(user_id)
        result = ""

        try:
            if cmd == "start":
                session_manager.clear(user_id)
                result = "Session reset. Welcome to Yolo!"

            elif cmd == "status":
                history_len = len(session.message_history)
                compact_threshold = yolo_agent.AUTO_COMPACT_THRESHOLD
                pending = len(session.pending_confirmations)
                mode = "YOLO (Full Access)" if session.yolo_mode else "Safe (HITL)"
                think = "ON" if getattr(session, "think_mode", False) else "OFF"
                policy = getattr(session, "think_mode_policy", "auto")
                result = (
                    f"**Status Report**\n"
                    f"- Mode: {mode}\n"
                    f"- Think mode: {think}\n"
                    f"- Think policy: `{policy}`\n"
                    f"- History: `{history_len}/{compact_threshold}` messages\n"
                    f"- Pending confirmations: **{pending}**\n"
                    f"- LLM calls: `{getattr(session, 'llm_call_count', 0)}`\n"
                    f"- Tokens: `{getattr(session, 'total_tokens', 0)}` "
                    f"(prompt: `{getattr(session, 'total_prompt_tokens', 0)}` "
                    f"+ completion: `{getattr(session, 'total_completion_tokens', 0)}`)\n"
                    f"- Model: `{yolo_agent.router.config.model}`\n"
                    f"- Provider: `{yolo_agent.router.config.provider}`"
                )

            elif cmd == "mode":
                if not args:
                    current = "YOLO" if session.yolo_mode else "Safe"
                    result = f"Current mode: **{current}**. Use `/mode yolo` or `/mode safe`."
                elif args[0].lower() == "yolo":
                    session.yolo_mode = True
                    result = "**YOLO Mode Enabled!** All actions execute without confirmation."
                elif args[0].lower() == "safe":
                    session.yolo_mode = False
                    result = "**Safe Mode Enabled.** Destructive actions require confirmation."
                else:
                    result = "Unknown mode. Use `/mode yolo` or `/mode safe`."
                session_manager.save(user_id)

            elif cmd == "think":
                if not args:
                    current = "On" if session.think_mode else "Off"
                    policy = getattr(session, "think_mode_policy", "auto")
                    result = f"Think mode: **{current}**. Policy: **{policy}**."
                elif args[0].lower() in {"on", "true", "enable"}:
                    session.think_mode_policy = "force_on"
                    session.think_mode = True
                    result = "**Think Mode Enabled.** Policy set to `force_on`."
                elif args[0].lower() in {"off", "false", "disable"}:
                    session.think_mode_policy = "force_off"
                    session.think_mode = False
                    result = "**Think Mode Disabled.** Policy set to `force_off`."
                elif args[0].lower() in {"auto", "smart", "default"}:
                    session.think_mode_policy = "auto"
                    session.think_mode = False
                    result = "**Think Mode Auto** enabled."
                else:
                    result = "Unknown option. Use `/think on`, `/think off`, or `/think auto`."
                session_manager.save(user_id)

            elif cmd == "compact":
                await yolo_agent._compact_history(session, yolo_agent.router)
                session_manager.save(user_id)
                result = f"History compacted. Now {len(session.message_history)} messages."

            elif cmd == "tools":
                import tools
                lines = ["**Available Tools:**\n"]
                for schema in tools.TOOLS_SCHEMAS:
                    name = schema["function"]["name"]
                    desc = schema["function"]["description"]
                    lines.append(f"- `{name}`: {desc}")
                result = "\n".join(lines)

            elif cmd == "experiences":
                from tools.experience_ops import list_experiences
                result = list_experiences(user_id)

            elif cmd == "schedules":
                from tools.cron_ops import get_scheduled_tasks
                result = get_scheduled_tasks(user_id)

            elif cmd == "memories":
                if args and args[0] == "--stats":
                    from tools.memory_ops import memory_stats
                    result = memory_stats(user_id)
                else:
                    from tools.memory_ops import memory_list
                    result = memory_list(user_id)

            elif cmd == "compact_memories":
                from tools.memory_ops import consolidate_memories
                result = consolidate_memories(user_id)

            elif cmd == "facts":
                if session.message_history and session.message_history[0].get("role") == "system":
                    content = str(session.message_history[0].get("content", ""))
                    facts = yolo_agent.extract_auto_basic_facts(content)
                    if facts:
                        lines = [f"{i+1}. {f}" for i, f in enumerate(facts)]
                        result = "**Auto Basic Facts:**\n\n" + "\n".join(lines)
                    else:
                        result = "No auto basic facts currently injected."
                else:
                    result = "No system prompt found for this session."

            elif cmd == "forget":
                from tools.memory_ops import memory_wipe
                result = memory_wipe(user_id)

            elif cmd == "cancel":
                if session.pending_confirmations:
                    for p in session.pending_confirmations:
                        session.message_history.append({
                            "role": "tool",
                            "tool_call_id": p["tool_call_id"],
                            "name": p["action"],
                            "content": "Action denied by user.",
                        })
                    count = len(session.pending_confirmations)
                    session.pending_confirmations = []
                    session.mark_dirty()
                    session_manager.save(user_id)
                    result = f"✅ {count} pending action(s) cancelled."
                else:
                    result = "No pending actions."

            else:
                result = (
                    f"Unknown command: `/{cmd}`. Available: "
                    "`/start`, `/status`, `/mode`, `/think`, `/compact`, `/tools`, "
                    "`/experiences`, `/schedules`, `/memories`, `/facts`, `/forget`, `/cancel`."
                )

        except Exception as exc:
            result = f"Error executing /{cmd}: {exc}"

    return web.json_response({"response": result, "command": cmd})


async def handle_health(request: web.Request) -> web.Response:
    """GET /health"""
    return web.json_response({
        "status": "ok",
        "model": yolo_agent.router.config.model,
        "provider": yolo_agent.router.config.provider,
        "default_user_id": DEFAULT_USER_ID,
    })


async def handle_session_info(request: web.Request) -> web.Response:
    """GET /session?user_id=N  — return current session state for the UI."""
    user_id = int(request.query.get("user_id", "1"))
    session = session_manager.get_or_create(user_id)

    # Extract message history (excluding system prompt) for the UI
    messages = []
    for msg in session.message_history:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role in ("user", "assistant"):
            content = msg.get("content", "")
            if content and not content.startswith("[CONVERSATION_SUMMARY]"):
                messages.append({"role": role, "content": content})

    return web.json_response({
        "user_id": user_id,
        "yolo_mode": session.yolo_mode,
        "think_mode": getattr(session, "think_mode", False),
        "think_mode_policy": getattr(session, "think_mode_policy", "auto"),
        "history_length": len(session.message_history),
        "pending_confirmations": len(session.pending_confirmations),
        "messages": messages,
        "llm_call_count": getattr(session, "llm_call_count", 0),
        "total_tokens": getattr(session, "total_tokens", 0),
    })


async def handle_get_workers(request: web.Request) -> web.Response:
    """GET /workers?user_id=N"""
    from tools.database_ops import list_background_tasks
    user_id = int(request.query.get("user_id", DEFAULT_USER_ID))
    tasks = list_background_tasks(user_id, limit=50)
    
    result = []
    for t in tasks:
        result.append({
            "task_id": t[0],
            "objective": t[1],
            "status": t[2],
            "created_at": str(t[3])
        })
    return web.json_response({"workers": result})


async def handle_get_swarms(request: web.Request) -> web.Response:
    """GET /swarms?user_id=N — Get unique swarms and their lead tasks."""
    from tools.database_ops import _conn_ctx
    user_id = int(request.query.get("user_id", DEFAULT_USER_ID))
    
    with _conn_ctx() as conn:
        cursor = conn.cursor()
        # Find all swarm_ids mentioned in objective or messages
        cursor.execute("SELECT DISTINCT swarm_id FROM swarm_messages")
        swarm_rows = cursor.fetchall()
        
        swarms = []
        for r in swarm_rows:
            swarm_id = r[0]
            # Get latest message for summary
            cursor.execute("SELECT created_at FROM swarm_messages WHERE swarm_id = ? ORDER BY created_at DESC LIMIT 1", (swarm_id,))
            last_msg = cursor.fetchone()
            
            # Find workers associated with this swarm
            cursor.execute("SELECT task_id, objective, status FROM background_tasks WHERE objective LIKE ?", (f"%{swarm_id}%",))
            # Extract role from the objective if possible (e.g. "[Lead Developer] ...")
            workers = []
            for w in cursor.fetchall():
                task_id, objective, status = w[0], w[1], w[2]
                role = "Worker"
                if objective.startswith("[") and "]" in objective:
                    role = objective[1:objective.find("]")]
                workers.append({"task_id": task_id, "role": role, "status": status})
            
            swarms.append({
                "swarm_id": swarm_id,
                "last_active": str(last_msg[0]) if last_msg else None,
                "workers": workers
            })
            
    return web.json_response({"swarms": swarms})


async def handle_get_swarm_messages(request: web.Request) -> web.Response:
    """GET /swarms/{swarm_id}/messages"""
    from tools.database_ops import get_swarm_messages
    swarm_id = request.match_info.get("swarm_id")
    if not swarm_id:
        return web.json_response({"error": "Missing swarm_id"}, status=400)
    
    messages = get_swarm_messages(swarm_id, limit=100)
    return web.json_response({"messages": messages})


async def handle_get_worker_session(request: web.Request) -> web.Response:
    """GET /workers/{task_id}/session"""
    from tools.database_ops import get_background_task_history
    task_id = request.match_info.get("task_id")
    if not task_id:
        return web.json_response({"error": "Missing task_id"}, status=400)
    
    history = get_background_task_history(task_id)
    
    messages = []
    for msg in history:
        role = msg.get("role", "")
        if role == "system":
            continue
        if role in ("user", "assistant", "tool"):
            messages.append(msg)
            
    return web.json_response({"messages": messages})


async def handle_get_sessions(request: web.Request) -> web.Response:
    """GET /sessions — list all unique user_id sessions in the database."""
    from tools.database_ops import list_sessions
    sessions = list_sessions()
    result = []
    for s in sessions:
        result.append({
            "user_id": s[0],
            "last_active": str(s[1])
        })
    return web.json_response({"sessions": result})


async def handle_transcribe(request: web.Request) -> web.Response:
    """POST /transcribe — transcribe audio data."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    audio_base64 = data.get("audio")
    if not audio_base64:
        return web.json_response({"error": "Missing audio data"}, status=400)

    import base64
    import tempfile
    from openai import OpenAI

    try:
        # Decode base64 to bytes
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("VISION_API_BASE_URL") or os.getenv("OPENAI_BASE_URL")

        if api_key or (base_url and base_url != "https://api.openai.com/v1"):
            client = OpenAI(api_key=api_key or "not-required", base_url=base_url)
            with open(tmp_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=os.getenv("TRANSCRIPTION_MODEL_NAME", "whisper-1"),
                    file=audio_file
                )
            text = getattr(transcript, "text", str(transcript))
        else:
            # Mock transcription for testing
            text = "This is a mock transcription of your voice message."
        # Cleanup
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        return web.json_response({"text": text})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

async def handle_update_env(request: web.Request) -> web.Response:
    """POST /config/env — Update LLM provider settings in settings.json"""
    try:
        from tools.settings import update_setting
        data = await request.json()
            
        allowed_keys = {
            "LLM_PROVIDER", "MODEL_NAME", "LLM_MODEL", 
            "OPENAI_API_KEY", "OPENAI_BASE_URL", 
            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL",
            "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
            "LLM_API_KEY", "LLM_BASE_URL"
        }
        
        for k, v in data.items():
            if k in allowed_keys:
                update_setting(k, str(v))
        
        yolo_agent.reload_router()
        return web.json_response({"status": "success", "message": "Settings saved and LLM router reloaded"})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

async def handle_get_mcp_servers(request: web.Request) -> web.Response:
    """GET /mcp/servers — Get current MCP configuration"""
    try:
        from tools.base import YOLO_HOME
        import json
        mcp_path = YOLO_HOME / "mcp_servers.json"
        if not mcp_path.exists():
            return web.json_response({"mcpServers": {}})
        with open(mcp_path, "r") as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

async def handle_post_mcp_servers(request: web.Request) -> web.Response:
    """POST /mcp/servers — Update MCP configuration"""
    try:
        from tools.base import YOLO_HOME
        from tools.mcp_manager import mcp_manager
        import json
        data = await request.json()
        
        mcp_path = YOLO_HOME / "mcp_servers.json"
        with open(mcp_path, "w") as f:
            json.dump(data, f, indent=4)
        
        # Reload MCP manager configuration
        await mcp_manager.cleanup()
        mcp_manager._connections_initialized = False
        await mcp_manager.initialize()
        
        return web.json_response({"status": "success", "message": "MCP servers updated and reloaded"})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


# ── App setup ──

def create_app() -> web.Application:
    # Set max payload size to 100MB to allow large file attachments
    app = web.Application(
        client_max_size=1024**2 * 100,
        middlewares=[bridge_security_middleware],
    )
    app.router.add_post("/chat", handle_chat)
    app.router.add_post("/chat/stream", handle_chat_stream)
    app.router.add_post("/confirm", handle_confirm)
    app.router.add_post("/command", handle_command)
    app.router.add_post("/transcribe", handle_transcribe)
    app.router.add_post("/config/env", handle_update_env)
    app.router.add_get("/mcp/servers", handle_get_mcp_servers)
    app.router.add_post("/mcp/servers", handle_post_mcp_servers)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/session", handle_session_info)
    app.router.add_get("/sessions", handle_get_sessions)
    app.router.add_get("/workers", handle_get_workers)
    app.router.add_get("/swarms", handle_get_swarms)
    app.router.add_get("/swarms/{swarm_id}/messages", handle_get_swarm_messages)
    app.router.add_get("/workers/{task_id}/session", handle_get_worker_session)
    
    # Serve static files from artifacts/uploads
    try:
        from tools.base import YOLO_ARTIFACTS
        app.router.add_static("/artifacts/", path=str(YOLO_ARTIFACTS), name="artifacts")
        
        uploads_dir = str(get_uploads_dir())
        app.router.add_static("/uploads/", path=uploads_dir, name="uploads")
    except Exception:
        pass
        
    return app


def init_session_manager(shared_manager: SessionManager = None):
    """Set the module-level session_manager. Accepts an external one for
    shared-gateway mode (when started from server.py alongside Telegram)."""
    global session_manager
    if shared_manager is not None:
        session_manager = shared_manager
    elif session_manager is None:
        session_manager = SessionManager(timeout_minutes=TIMEOUT_MINUTES)
    return session_manager


async def run_desktop_bridge(
    host: str = "127.0.0.1",
    port: int = 0,
    shared_session_manager: SessionManager = None,
) -> None:
    """Start the desktop bridge as an async task (called from server.py).

    This runs forever alongside Telegram/Discord gateways.
    """
    if port == 0:
        port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))

    init_session_manager(shared_session_manager)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print(f"[desktop-bridge] Listening on http://{host}:{port}")
    print("[desktop-bridge] Session shared with Telegram/CLI/Discord")
    sys.stdout.flush()

    # Run forever (until cancelled)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()
        raise


def main():
    """Standalone entry point (for development / testing)."""
    init_session_manager()
    port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))
    app = create_app()

    print(f"[desktop-bridge] Starting on http://127.0.0.1:{port}")
    print(f"[desktop-bridge] Model: {yolo_agent.router.config.model} via {yolo_agent.router.config.provider}")
    print("[desktop-bridge] Session DB: ~/.yolo/yolo_v2.db (shared with Telegram/CLI)")
    print("[desktop-bridge] Bridge ready")
    sys.stdout.flush()

    try:
        web.run_app(app, host="127.0.0.1", port=port, print=None)
    except OSError as e:
        if e.errno == 98:
            print(f"[desktop-bridge] Port {port} is already in use. Assuming bridge is already running.")
        else:
            raise


if __name__ == "__main__":
    main()


async def run_desktop_bridge(
    host: str = "127.0.0.1",
    port: int = 0,
    shared_session_manager: SessionManager = None,
) -> None:
    """Start the desktop bridge as an async task (called from server.py).

    This runs forever alongside Telegram/Discord gateways.
    """
    if port == 0:
        port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))

    init_session_manager(shared_session_manager)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print(f"[desktop-bridge] Listening on http://{host}:{port}")
    print("[desktop-bridge] Session shared with Telegram/CLI/Discord")
    sys.stdout.flush()

    # Run forever (until cancelled)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()
        raise


def main():
    """Standalone entry point (for development / testing)."""
    init_session_manager()
    port = int(os.getenv("DESKTOP_BRIDGE_PORT", "8790"))
    app = create_app()

    print(f"[desktop-bridge] Starting on http://127.0.0.1:{port}")
    print(f"[desktop-bridge] Model: {yolo_agent.router.config.model} via {yolo_agent.router.config.provider}")
    print("[desktop-bridge] Session DB: ~/.yolo/yolo_v2.db (shared with Telegram/CLI)")
    print("[desktop-bridge] Bridge ready")
    sys.stdout.flush()

    try:
        web.run_app(app, host="127.0.0.1", port=port, print=None)
    except OSError as e:
        if e.errno == 98:
            print(f"[desktop-bridge] Port {port} is already in use. Assuming bridge is already running.")
        else:
            raise


if __name__ == "__main__":
    main()
