import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from colorama import Fore, init
from tools.settings import load_settings

import tools
from tools.base import YOLO_HOME
from llm_router import LLMRouter, load_llm_config
from session import Session
from tool_dispatcher import execute_tool_direct, sanitize_history

from prompt_builder import (
    get_initial_messages,
    _normalize_single_system_message,
    _fetch_all_memories,
    _sync_basic_facts_into_system_prompt,
    _is_complex_task_prompt,
    _inject_system_directive,
    THINK_MODE_SYSTEM_DIRECTIVE,
    _build_memory_context,
    _merge_memory_context_into_system_prompt,
    _is_self_upgrade_request,
    SELF_UPGRADE_SYSTEM_DIRECTIVE,
    _is_experience_update_request,
    EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE,
    log_agent,
    _is_gui_interaction_request,
    GUI_PERCEPTION_DIRECTIVE,
    _is_out_of_scope,
    _is_destructive_or_sensitive_tool,
    _extract_tool_path,
    PendingConfirmationError,
    _compact_history,
    _collect_turn_tool_names,
    _collect_run_bash_commands,
    _missing_self_upgrade_phases,
    _repo_has_tests,
)
from tools.mcp_manager import mcp_manager

class TUIMessage:
    STREAM = "__STREAM__"
    STATUS = "__STATUS__"
    TOOL_CALL = "__TOOL_CALL__"
    TOOL_RESULT = "__TOOL_RESULT__"
    DONE = "__DONE__"

init(autoreset=True)
load_settings()

VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"

def _get_router() -> LLMRouter:
    """Helper to load configuration and return a router instance."""
    config = load_llm_config()
    if not config.model:
        raise ValueError("No LLM model configured.")
    return LLMRouter(config)

router = _get_router()

def reload_router():
    """Manually reload the global router (useful for tests or env changes)."""
    global router
    router = _get_router()


def _get_active_router(session: Session) -> LLMRouter:
    """Get the correct LLMRouter instance for the session."""
    if getattr(session, "llm_model", None):
        config = load_llm_config()
        config.model = session.llm_model
        return LLMRouter(config)
    return router
AUTO_COMPACT_THRESHOLD = int(os.getenv("AUTO_COMPACT_THRESHOLD", "40"))
_LOCAL_PROMPTS_DIR = Path(__file__).resolve().parent / "configs" / "prompts"
PROMPTS_DIR = (YOLO_HOME / "prompts") if (YOLO_HOME / "prompts").is_dir() else _LOCAL_PROMPTS_DIR


def _append_tool_result(
    session: Session,
    *,
    tool_call_id: str,
    name: str,
    content: str,
) -> None:
    session.message_history.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": content,
        }
    )
    session.mark_dirty()


def _turn_state(user_msg: Optional[Any], session: Session, memory_service: Any) -> dict:
    state = {
        "self_upgrade_active": False,
        "self_upgrade_start_index": len(session.message_history),
        "experience_update_active": False,
        "experience_update_start_index": len(session.message_history),
    }

    if not session.message_history:
        session.message_history = get_initial_messages()

    _normalize_single_system_message(session)

    all_memories = (
        _fetch_all_memories(memory_service, session.user_id) if memory_service else []
    )

    _sync_basic_facts_into_system_prompt(
        session, memory_service, all_results=all_memories
    )

    if getattr(session, "think_mode_policy", "auto") == "auto" and user_msg is not None:
        session.think_mode = _is_complex_task_prompt(user_msg)

    if getattr(session, "think_mode", False):
        _inject_system_directive(session, THINK_MODE_SYSTEM_DIRECTIVE)

    if user_msg:
        memory_context = _build_memory_context(
            memory_service, session.user_id, user_msg, all_results=all_memories
        )
        _merge_memory_context_into_system_prompt(session, memory_context)
        
        # Skill Discovery & Strategy Nudge
        if getattr(session, "llm_call_count", 0) > 0 and session.llm_call_count % 15 == 0:
            nudge_directive = (
                "\n[System note: You have been iterating on this task for a while. "
                "If you feel stuck or are repeating the same generic bash commands, "
                "remember to utilize your advanced tools: delegate to subagents, "
                "search for specialized skills, or read logs/memory comprehensively.]"
            )
            _inject_system_directive(session, nudge_directive)

        if _is_self_upgrade_request(user_msg):
            state["self_upgrade_active"] = True
            _inject_system_directive(session, SELF_UPGRADE_SYSTEM_DIRECTIVE)
            state["self_upgrade_start_index"] = len(session.message_history)

        if _is_experience_update_request(user_msg):
            state["experience_update_active"] = True
            _inject_system_directive(session, EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE)
            state["experience_update_start_index"] = len(session.message_history)

        session.message_history.append({"role": "user", "content": user_msg})
        session.mark_dirty()
        log_agent(session.user_id, "IN", user_msg, Fore.CYAN)

        if _is_gui_interaction_request(user_msg):
            _inject_system_directive(session, GUI_PERCEPTION_DIRECTIVE)
    else:
        # Recover state if resuming without a new user message
        if session.message_history and session.message_history[0].get("role") == "system":
            sys_content = session.message_history[0].get("content") or ""
            if SELF_UPGRADE_SYSTEM_DIRECTIVE in sys_content:
                state["self_upgrade_active"] = True
                for i in range(len(session.message_history) - 1, -1, -1):
                    msg = session.message_history[i]
                    content = msg.get("content") or ""
                    if msg.get("role") == "user" and _is_self_upgrade_request(content):
                        state["self_upgrade_start_index"] = i
                        break
            if EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE in sys_content:
                state["experience_update_active"] = True
                for i in range(len(session.message_history) - 1, -1, -1):
                    msg = session.message_history[i]
                    content = msg.get("content") or ""
                    if msg.get("role") == "user" and _is_experience_update_request(content):
                        state["experience_update_start_index"] = i
                        break

    _normalize_single_system_message(session)
    return state


def _find_unanswered_tool_calls(session: Session) -> list[dict]:
    assistant_msg = None
    assistant_idx = None
    for i in range(len(session.message_history) - 1, -1, -1):
        msg = session.message_history[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            assistant_msg = msg
            assistant_idx = i
            break

    if assistant_msg is None:
        return []

    answered = {
        m["tool_call_id"]
        for m in session.message_history[assistant_idx + 1:]
        if m.get("role") == "tool"
    }
    return [tc for tc in assistant_msg["tool_calls"] if tc["id"] not in answered]


def _is_nested_background_mission(session: Session, func_name: str) -> bool:
    if func_name != "run_background_mission":
        return False
    system_prompt = ""
    if session.message_history and session.message_history[0].get("role") == "system":
        system_prompt = session.message_history[0].get("content", "")
    return "detached background mission" in system_prompt.lower()


async def _execute_unanswered_tool_calls(
    unanswered: list[dict],
    session: Session,
    signal_handler: Optional[Callable],
) -> bool:
    if not unanswered:
        return False

    log_agent(
        session.user_id,
        "RESUME",
        f"Completing turn with {len(unanswered)} tool calls...",
        Fore.YELLOW,
    )

    if signal_handler:
        tool_names_str = ", ".join(set(tc["function"]["name"] for tc in unanswered))
        await signal_handler(f"__STATUS__: Executing tools: {tool_names_str}")

    tasks = []
    session.pending_confirmations = []

    for tool_call in unanswered:
        func_name = tool_call["function"]["name"]
        tc_id = tool_call["id"]
        try:
            args = json.loads(
                tool_call["function"].get("arguments", "{}"),
                strict=False,
            )
        except Exception:
            args = {}

        if not isinstance(args, dict):
            args = {}

        if "_invalid_json" in args:
            res = f"Error: Your tool call arguments were not valid JSON. Exception: {args.get('_error')}\nYou sent: {args.get('_invalid_json')}\nPlease fix your JSON syntax (e.g. properly escape newlines as \\n and quotes) and try again."
            _append_tool_result(
                session, tool_call_id=tc_id, name=func_name, content=res
            )
            continue

        if _is_nested_background_mission(session, func_name):
            _append_tool_result(
                session,
                tool_call_id=tc_id,
                name=func_name,
                content="Skipping nested `run_background_mission` call: already running in background mode.",
            )
            continue

        out_of_scope = _is_out_of_scope(args)
        if (_is_destructive_or_sensitive_tool(func_name) or out_of_scope) and not session.yolo_mode:
            _append_tool_result(
                session,
                tool_call_id=tc_id,
                name=func_name,
                content="[HITL_PENDING]",
            )
            session.pending_confirmations.append(
                {
                    "action": func_name,
                    "path": _extract_tool_path(args),
                    "args": args,
                    "tool_call_id": tc_id,
                }
            )
            continue

        async def run_and_store(name=func_name, arguments=args, call_id=tc_id):
            try:
                result = await execute_tool_direct(
                    name,
                    arguments,
                    session.user_id,
                    signal_handler,
                    session=session,
                    call_id=call_id,
                    confirmed=session.yolo_mode,
                )
                return {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": result,
                }
            except Exception as e:
                return {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": f"Tool execution error: {e}",
                }

        tasks.append(run_and_store())

    if tasks:
        results = await asyncio.gather(*tasks)
        for r in results:
            session.message_history.append(r)
        session.mark_dirty()

    if session.pending_confirmations:
        if signal_handler:
            await signal_handler("__STATUS__: ")
        first = session.pending_confirmations[0]
        raise PendingConfirmationError(
            first["action"],
            first["path"],
            first["tool_call_id"],
            first["args"],
        )

    return True


def _deep_merge_tool_delta(target: dict, source: dict) -> None:
    for key, value in source.items():
        if key == "index":
            continue
        if isinstance(value, dict):
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            _deep_merge_tool_delta(target[key], value)
        elif isinstance(value, str) and key in target and isinstance(target[key], str):
            target[key] = target[key] + value if key in {"name", "arguments"} else value
        else:
            target[key] = value


def _normalize_tool_calls(tool_calls_acc: list) -> list[dict]:
    valid_tool_calls = []
    for tc in tool_calls_acc:
        if not tc.get("function", {}).get("name"):
            continue

        args = tc["function"].get("arguments")
        if isinstance(args, dict):
            tc["function"]["arguments"] = json.dumps(args)
        elif not args or not isinstance(args, str):
            tc["function"]["arguments"] = "{}"
        else:
            try:
                json.loads(tc["function"]["arguments"], strict=False)
            except Exception as e:
                tc["function"]["arguments"] = json.dumps(
                    {"_invalid_json": tc["function"]["arguments"], "_error": str(e)}
                )

        if not tc.get("id"):
            tc["id"] = f"call_{uuid.uuid4().hex[:12]}"

        valid_tool_calls.append(tc)
    return valid_tool_calls


def zip_history_payload(messages: list, session: Session) -> list:
    """Compress and compact message payload to avoid LLM usage limits."""
    zipping_enabled = os.getenv("REQUEST_ZIPPING", "true").lower() == "true"
    if not zipping_enabled:
        return messages

    try:
        threshold = int(os.getenv("REQUEST_ZIPPING_THRESHOLD", "4000"))
    except ValueError:
        threshold = 4000

    try:
        keep_head = int(os.getenv("REQUEST_ZIPPING_KEEP_HEAD", "1500"))
    except ValueError:
        keep_head = 1500

    try:
        keep_tail = int(os.getenv("REQUEST_ZIPPING_KEEP_TAIL", "1000"))
    except ValueError:
        keep_tail = 1000

    zipped = []
    for msg in messages:
        msg_copy = dict(msg)
        content = msg_copy.get("content")
        role = msg_copy.get("role")
        
        if not content:
            zipped.append(msg_copy)
            continue

        if isinstance(content, str):
            if len(content) > threshold:
                original_len = len(content)
                msg_copy["content"] = (
                    content[:keep_head]
                    + f"\n\n... [REQUEST ZIPPED: Truncated {original_len - (keep_head + keep_tail)} characters to avoid usage limits] ...\n\n"
                    + content[-keep_tail:]
                )
                from prompt_builder import log_agent
                from colorama import Fore
                log_agent(
                    session.user_id,
                    "ZIP",
                    f"Zipped message content of role '{role}' ({original_len} -> {len(msg_copy['content'])} chars) to avoid usage limits.",
                    Fore.CYAN
                )
        elif isinstance(content, list):
            new_list = []
            changed = False
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    text = item["text"]
                    if len(text) > threshold:
                        original_len = len(text)
                        zipped_text = (
                            text[:keep_head]
                            + f"\n\n... [REQUEST ZIPPED: Truncated {original_len - (keep_head + keep_tail)} characters to avoid usage limits] ...\n\n"
                            + text[-keep_tail:]
                        )
                        item_copy = dict(item)
                        item_copy["text"] = zipped_text
                        new_list.append(item_copy)
                        changed = True
                        from prompt_builder import log_agent
                        from colorama import Fore
                        log_agent(
                            session.user_id,
                            "ZIP",
                            f"Zipped multimodal text item of role '{role}' ({original_len} -> {len(zipped_text)} chars) to avoid usage limits.",
                            Fore.CYAN
                        )
                        continue
                new_list.append(item)
            if changed:
                msg_copy["content"] = new_list

        zipped.append(msg_copy)
    return zipped


async def _stream_llm_round(
    session: Session,
    current_tools: list,
    signal_handler: Optional[Callable],
) -> tuple[Optional[dict], Optional[str]]:
    max_llm_retries = 3
    active_router = _get_active_router(session)

    for llm_attempt in range(max_llm_retries):
        full_content = ""
        full_reasoning_content = ""
        tool_calls_acc: list = []
        usage = None
        has_choices = False
        last_stream_time = 0.0

        try:
            zipped_messages = zip_history_payload(session.message_history, session)
            response = await active_router.chat_completions(
                messages=zipped_messages,
                tools=current_tools,
                tool_choice="auto",
                stream=True,
            )

            async for chunk in response:
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage

                if not getattr(chunk, "choices", None):
                    continue

                has_choices = True
                delta = chunk.choices[0].delta

                if getattr(delta, "content", None):
                    full_content += delta.content
                    now = time.time()
                    if now - last_stream_time > 0.1 and signal_handler:
                        await signal_handler(f"__STREAM__:{full_content}")
                        last_stream_time = now

                reasoning = getattr(delta, "reasoning_content", None) or getattr(
                    delta, "reasoning", None
                )
                if reasoning:
                    full_reasoning_content += reasoning

                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", None) or 0
                        while len(tool_calls_acc) <= idx:
                            tool_calls_acc.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        _deep_merge_tool_delta(
                            tool_calls_acc[idx], tc.model_dump(exclude_none=True)
                        )

            if not has_choices and not usage:
                return None, "Error: No AI response."

            if full_content and signal_handler:
                await signal_handler(f"__STREAM__:{full_content}")
                await signal_handler("__STREAM_END__:")

            return {
                "content": full_content,
                "reasoning_content": full_reasoning_content,
                "tool_calls": tool_calls_acc,
                "usage": usage,
            }, None

        except Exception as e:
            from error_classifier import classify_api_error, FailoverReason
            classified = classify_api_error(e)
            
            if classified.retryable and llm_attempt < max_llm_retries - 1:
                if classified.reason == FailoverReason.CONTEXT_OVERFLOW:
                    log_agent(session.user_id, "SYSTEM", "Context overflow detected. Attempting to compress context...", Fore.YELLOW)
                    # Trigger compaction and retry immediately
                    await _compact_history(session, active_router)
                    continue
                    
                delay = classified.recommended_delay * (llm_attempt + 1)
                log_agent(
                    session.user_id,
                    "RETRY",
                    f"LLM failover triggered ({classified.reason.value}). Retrying in {delay}s ({llm_attempt + 1}/{max_llm_retries})...",
                    Fore.YELLOW,
                )
                if signal_handler:
                    await signal_handler(
                        f"__STATUS__: API issue ({classified.reason.value}), retrying ({llm_attempt + 1})..."
                    )
                await asyncio.sleep(delay)
                continue
            return None, f"Error: LLM issue: {e}"

    return None, "Error: No AI response."


def _record_llm_usage(session: Session, usage: Any) -> None:
    if usage:
        session.total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        session.total_completion_tokens += (
            getattr(usage, "completion_tokens", 0) or 0
        )
        session.total_tokens += getattr(usage, "total_tokens", 0) or 0
    session.llm_call_count += 1


def _append_assistant_round(session: Session, round_result: dict) -> bool:
    msg_dict: dict[str, Any] = {
        "role": "assistant",
        "content": round_result["content"],
    }
    if round_result["reasoning_content"]:
        msg_dict["reasoning_content"] = round_result["reasoning_content"]

    valid_tool_calls = _normalize_tool_calls(round_result["tool_calls"])
    if valid_tool_calls:
        msg_dict["tool_calls"] = valid_tool_calls

    session.message_history.append(msg_dict)
    session.mark_dirty()
    return bool(valid_tool_calls)


async def _finalize_or_request_more_work(
    *,
    session: Session,
    user_msg: Optional[Any],
    memory_service: Any,
    full_content: str,
    turn_state: dict,
    signal_handler: Optional[Callable],
) -> Optional[str]:
    if turn_state["self_upgrade_active"]:
        used_tools = _collect_turn_tool_names(
            session.message_history, turn_state["self_upgrade_start_index"]
        )
        run_bash_commands = _collect_run_bash_commands(
            session.message_history,
            turn_state["self_upgrade_start_index"],
        )
        missing = _missing_self_upgrade_phases(
            used_tools,
            run_bash_commands=run_bash_commands,
            require_pytest=_repo_has_tests(),
        )
        if missing:
            guidance = (
                "Before finishing, you must complete all SELF-UPGRADE phases. "
                f"Missing phases: {', '.join(missing)}. "
                "Continue by calling tools to complete missing phases, then finalize. "
                "If `validation_pytest` is missing, run at least one `pytest` command via `run_bash`."
            )
            session.message_history.append({"role": "user", "content": guidance})
            session.mark_dirty()
            return None

    if turn_state["experience_update_active"]:
        used_tools = _collect_turn_tool_names(
            session.message_history,
            turn_state["experience_update_start_index"],
        )
        if "learn_experience" not in used_tools:
            guidance = (
                "Before finishing, execute `learn_experience` at least once to persist the lesson. "
                "Then provide confirmation that the experience was actually stored."
            )
            session.message_history.append({"role": "user", "content": guidance})
            session.mark_dirty()
            return None

    if memory_service and user_msg:
        try:
            memory_service.add(
                [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": full_content},
                ],
                user_id=str(session.user_id),
            )
        except Exception as e:
            from tools.base import audit_log
            audit_log("auto_memory_add", {"user_id": session.user_id}, "error", str(e))

    if signal_handler:
        await signal_handler("__STATUS__: ")
    return full_content or "Task completed."


def _detect_tool_loop(session: Session, limit: int = 5) -> Optional[str]:
    """Detect if the agent is stuck calling the same tool with identical arguments consecutively."""
    history = session.message_history
    if not history:
        return None

    tool_calls = []
    for msg in reversed(history):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name")
                if name in ("check_workers", "get_worker_status", "read_swarm_messages"):
                    continue
                try:
                    args = json.dumps(func.get("arguments"), sort_keys=True)
                except Exception:
                    args = str(func.get("arguments"))
                tool_calls.append((name, args))
                if len(tool_calls) >= limit:
                    break
        if len(tool_calls) >= limit:
            break

    if len(tool_calls) < limit:
        return None

    first = tool_calls[0]
    if all(tc == first for tc in tool_calls):
        return (
            f"Agent loop detected: The tool '{first[0]}' was called {limit} times consecutively "
            f"with the same arguments ({first[1]}). Breaking iteration loop to prevent infinite execution."
        )
    return None


async def run_agent_turn(
    user_msg: Optional[Any],
    session: Session,
    signal_handler: Optional[Callable] = None,
    memory_service: Any = None,
) -> str:
    turn_state = _turn_state(user_msg, session, memory_service)

    max_agent_iterations = int(os.getenv("AGENT_MAX_ITERATIONS", "50"))
    agent_iterations = 0
    while agent_iterations < max_agent_iterations:
        agent_iterations += 1

        loop_error = _detect_tool_loop(session)
        if loop_error:
            log_agent(session.user_id, "WARN", loop_error, Fore.RED)
            return loop_error

        if session.pending_confirmations:
            if signal_handler:
                await signal_handler("__STATUS__: ")
            first = session.pending_confirmations[0]
            raise PendingConfirmationError(
                first["action"],
                first["path"],
                first["tool_call_id"],
                first["args"],
            )

        if await _execute_unanswered_tool_calls(
            _find_unanswered_tool_calls(session), session, signal_handler
        ):
            continue

        _normalize_single_system_message(session)

        if len(session.message_history) > AUTO_COMPACT_THRESHOLD:
            await _compact_history(session, _get_active_router(session))

        log_agent(session.user_id, "THINKING", "Consulting LLM...", Fore.MAGENTA)
        if signal_handler:
            await signal_handler("__STATUS__: Consulting AI model...")

        if getattr(session, "history_dirty", True):
            session.message_history = sanitize_history(session.message_history)
            session.history_dirty = False

        await mcp_manager.initialize()
        round_result, error = await _stream_llm_round(
            session, tools.TOOLS_SCHEMAS + mcp_manager.tool_schemas, signal_handler
        )
        if error:
            return error

        _record_llm_usage(session, round_result["usage"])
        has_tool_calls = _append_assistant_round(session, round_result)
        if has_tool_calls:
            continue

        final = await _finalize_or_request_more_work(
            session=session,
            user_msg=user_msg,
            memory_service=memory_service,
            full_content=round_result["content"],
            turn_state=turn_state,
            signal_handler=signal_handler,
        )
        if final is not None:
            return final

    log_agent(session.user_id, "WARN", "Agent hit max iteration limit", Fore.RED)
    return "I've reached my maximum number of processing steps. Please try again with a more specific request."


async def resolve_confirmations(
    session: Session, 
    user_id: int, 
    signal_handler: Optional[Callable] = None,
    confirm_all: bool = True
) -> str:
    """Execute pending tool calls that were approved by the user."""
    if not session.pending_confirmations:
        return "No pending actions to confirm."

    pending_list = list(session.pending_confirmations)
    if confirm_all:
        session.pending_confirmations = []
    else:
        # Resolve only the first one
        p = pending_list[0]
        pending_list = [p]
        session.pending_confirmations = session.pending_confirmations[1:]

    execution_tasks = []
    for p in pending_list:
        execution_tasks.append(
            execute_tool_direct(
                p["action"],
                p["args"],
                user_id,
                signal_handler=signal_handler,
                session=session,
                call_id=p["tool_call_id"],
                confirmed=True,
            )
        )

    results = await asyncio.gather(*execution_tasks, return_exceptions=True)

    # Update history for each
    for p, result in zip(pending_list, results):
        if isinstance(result, Exception):
            result = f"Tool execution error: {result}"
        found = False
        for msg in reversed(session.message_history):
            if (
                msg.get("role") == "tool"
                and msg.get("tool_call_id") == p["tool_call_id"]
            ):
                msg["content"] = result
                found = True
                break
        if not found:
            session.message_history.append(
                {
                    "role": "tool",
                    "tool_call_id": p["tool_call_id"],
                    "name": p["action"],
                    "content": result,
                }
            )
    session.mark_dirty()
    
    # After resolving, run the agent turn again to process results
    return await run_agent_turn(None, session, signal_handler=signal_handler)


async def deny_confirmations(session: Session, deny_all: bool = True) -> None:
    """Reject pending tool calls as requested by the user."""
    if not session.pending_confirmations:
        return

    pending_list = list(session.pending_confirmations)
    if deny_all:
        session.pending_confirmations = []
    else:
        session.pending_confirmations = session.pending_confirmations[1:]
        pending_list = [pending_list[0]]

    for p in pending_list:
        found = False
        for msg in reversed(session.message_history):
            if (
                msg.get("role") == "tool"
                and msg.get("tool_call_id") == p["tool_call_id"]
            ):
                msg["content"] = "Action denied by user."
                found = True
                break
        if not found:
            session.message_history.append(
                {
                    "role": "tool",
                    "tool_call_id": p["tool_call_id"],
                    "name": p["action"],
                    "content": "Action denied by user.",
                }
            )
    session.mark_dirty()


def main():
    import cli
    cli.main()


if __name__ == "__main__":
    main()
