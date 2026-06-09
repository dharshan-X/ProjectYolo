import os
import re
import json
from datetime import datetime, timezone
from colorama import Fore, Style
from typing import Optional, List, Dict, Any
from session import Session
from llm_router import load_llm_config, LLMRouter
from pathlib import Path
from tools.base import YOLO_HOME

VERBOSE = os.getenv("VERBOSE", "false").lower() == "true"
_LOCAL_PROMPTS_DIR = Path(__file__).resolve().parent / "configs" / "prompts"
PROMPTS_DIR = (YOLO_HOME / "prompts") if (YOLO_HOME / "prompts").is_dir() else _LOCAL_PROMPTS_DIR
_REPO_HAS_TESTS_CACHE: Optional[bool] = None
AUTO_FACTS_START = "[AUTO_BASIC_FACTS]"
AUTO_FACTS_END = "[/AUTO_BASIC_FACTS]"
MEMORY_CONTEXT_TRANSIENT_START = "[MEMORY_CONTEXT]"
MEMORY_CONTEXT_TRANSIENT_END = "[/MEMORY_CONTEXT]"
LEGACY_APPENDIX_START = "[LEGACY_SYSTEM_APPENDIX]"
LEGACY_APPENDIX_END = "[/LEGACY_SYSTEM_APPENDIX]"


_PROMPT_TEMPLATE_CACHE: Dict[str, tuple[str, float]] = {}
_IDENTITY_PROFILE_CACHE: Optional[tuple[str, float]] = None

def _get_text_content(content: Any) -> str:
    """Extract string text from potentially multi-modal message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Multi-modal list: [{"type": "text", "text": "..."}, {"type": "image_url", ...}]
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return " ".join(parts).strip()
    return ""


def _is_small_model_name(model_name: str) -> bool:
    match = re.search(r"(\d+(?:\.\d+)?)b", (model_name or "").lower())
    if not match:
        return False
    try:
        return float(match.group(1)) <= 3.0
    except Exception:
        return False


def _use_unified_prompt_architecture() -> bool:
    version = os.getenv("YOLO_SYSTEM_PROMPT_VERSION", "unified").strip().lower()
    return version not in {"legacy", "v0", "off", "false", "0"}


def _resolve_prompt_profile(profile: Optional[str] = None) -> str:
    explicit = (profile or "").strip().lower()
    if explicit in {"verbose", "compact"}:
        return explicit

    env_profile = os.getenv("YOLO_SYSTEM_PROMPT_PROFILE", "auto").strip().lower()
    if env_profile in {"verbose", "compact"}:
        return env_profile

    config = load_llm_config()
    return "compact" if _is_small_model_name(config.model or "") else "verbose"


def _load_prompt_template(name: str) -> Optional[str]:
    # Check user override directory first
    user_prompts_dir = YOLO_HOME / "prompts"
    user_path = user_prompts_dir / f"{name}.md"
    
    path = user_path if user_path.exists() else (PROMPTS_DIR / f"{name}.md")
    
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0

    if name in _PROMPT_TEMPLATE_CACHE:
        cached_content, cached_mtime = _PROMPT_TEMPLATE_CACHE[name]
        if cached_mtime == mtime and mtime != 0.0:
            return cached_content or None
            
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        content = ""

    _PROMPT_TEMPLATE_CACHE[name] = (content, mtime)
    return content or None


def _load_identity_profile() -> Optional[str]:
    """Load the master identity profile from YOLO_HOME or project configs.

    Priority: ~/.yolo/identity.md > <project>/configs/identity.md
    Result is cached and refreshed when the file's mtime changes.
    """
    global _IDENTITY_PROFILE_CACHE

    project_identity = Path(__file__).resolve().parent / "configs" / "identity.md"
    home_identity = YOLO_HOME / "identity.md"

    # Prefer YOLO_HOME, fall back to project-local
    path = home_identity if home_identity.exists() else project_identity
    if not path.exists():
        return None

    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0

    if _IDENTITY_PROFILE_CACHE is not None:
        cached_content, cached_mtime = _IDENTITY_PROFILE_CACHE
        if cached_mtime == mtime and mtime != 0.0:
            return cached_content or None

    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        content = ""

    _IDENTITY_PROFILE_CACHE = (content, mtime)
    return content or None


def _render_prompt_template(
    template: str,
    *,
    basic_facts: Optional[List[str]] = None,
    identity_hints: Optional[List[str]] = None,
) -> str:
    facts = basic_facts or ["(none yet)"]
    hints = identity_hints or ["(none yet)"]

    identity_profile = _load_identity_profile() or ""

    rendered = template
    rendered = rendered.replace("{{identity_profile}}", identity_profile)
    rendered = rendered.replace("{{basic_facts}}", "\n".join(f"- {f}" for f in facts))
    rendered = rendered.replace(
        "{{identity_hints}}", "\n".join(f"- {h}" for h in hints)
    )
    return rendered.strip()


def _strip_tag_block(content: str, start_tag: str, end_tag: str) -> str:
    start = content.find(start_tag)
    if start == -1:
        return content
    end = content.find(end_tag, start)
    if end == -1:
        return content[:start].rstrip()
    return (content[:start] + content[end + len(end_tag) :]).rstrip()


def _replace_tag_block(
    content: str,
    start_tag: str,
    end_tag: str,
    body: Optional[str],
) -> str:
    base = _strip_tag_block(content, start_tag, end_tag)
    if not body or not body.strip():
        return base
    return base.rstrip() + f"\n\n{start_tag}\n{body.strip()}\n{end_tag}"


def _extract_memory_context_payload(memory_context: str) -> str:
    lines = (memory_context or "").splitlines()
    if lines and lines[0].strip() == "[MEMORY_CONTEXT]":
        lines = lines[1:]
    if lines and lines[-1].strip() == "[/MEMORY_CONTEXT]":
        lines = lines[:-1]
    return "\n".join(line for line in lines if line.strip()).strip()


async def _compact_history(session: Session, router: LLMRouter) -> None:
    if len(session.message_history) <= 10:
        return

    log_agent(
        session.user_id,
        "COMPACT",
        f"Compacting history ({len(session.message_history)} messages)...",
        Fore.YELLOW,
    )

    # Identify system prompt
    system_prompt = None
    if session.message_history and session.message_history[0].get("role") == "system":
        system_prompt = session.message_history[0]

    # Keep last N messages to maintain immediate context, ensuring we don't sever tool call sequences.
    # We walk backward until we find a 'user' message, which is always safe to start a sequence with.
    keep_last = 6
    while keep_last < len(session.message_history):
        if session.message_history[-keep_last].get("role") == "user":
            break
        keep_last += 1

    if system_prompt:
        to_summarize = session.message_history[1:-keep_last]
    else:
        to_summarize = session.message_history[:-keep_last]

    last_messages = session.message_history[-keep_last:]

    if not to_summarize:
        return

    summary_request = (
        "Summarize the following technical conversation history concisely. "
        "Preserve all specific mission objectives, file paths, tool results, "
        "and established project preferences. Use Markdown bullet points."
    )

    # Truncate to avoid exceeding model context
    history_json = json.dumps(to_summarize)
    MAX_COMPACTION_CHARS = 50000
    if len(history_json) > MAX_COMPACTION_CHARS:
        history_json = history_json[:MAX_COMPACTION_CHARS] + '\n[TRUNCATED — history too large for full compaction]'

    try:
        resp = await router.chat_completions(
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior engineer summarizing a project's state.",
                },
                {
                    "role": "user",
                    "content": f"{summary_request}\n\nCONVERSATION HISTORY:\n{history_json}",
                },
            ],
            tools=[],
        )
        
        if not getattr(resp, "choices", None) or not resp.choices:
            log_agent(session.user_id, "ERROR", "Failed to compact history: empty choices returned by LLM.", Fore.RED)
            return

        summary = resp.choices[0].message.content

        new_history = []
        if system_prompt:
            new_history.append(system_prompt)

        new_history.append(
            {"role": "assistant", "content": f"[CONVERSATION_SUMMARY]\n{summary}"}
        )
        new_history.extend(last_messages)

        session.message_history = new_history
        session.mark_dirty()
        log_agent(
            session.user_id, "COMPACT", "History successfully compacted.", Fore.GREEN
        )
    except Exception as e:
        log_agent(session.user_id, "ERROR", f"Failed to compact history: {e}", Fore.RED)


LEGACY_SELF_UPGRADE_SYSTEM_DIRECTIVE = (
    "SELF-UPGRADE PROTOCOL (MANDATORY FOR THIS REQUEST): "
    "You are being asked to add a new capability to yourself. "
    "Complete these phases before giving a final answer: "
    "(1) Research: use at least one research tool (`web_search`, `browse_url`, browser tools, or `mcp_*`) to gather external guidance. "
    "(2) Implement: modify your own code using file tools. "
    "(3) Validate: run tests/validation with `run_bash` (or at minimum compile checks). "
    "If tests exist in this repository, run at least one `pytest` command. "
    "(4) Evolve memory/skills: record what changed using `learn_experience`, `archive_proactive_memory`, or `self_upgrade_summary`, and update/add a reusable skill with `optimize_skill` or `develop_new_skill` when relevant. "
    "Then provide a concise completion report including what was researched, what was changed, and validation results."
)


LEGACY_EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE = (
    "EXPERIENCE UPDATE PROTOCOL: "
    "When the user asks to update, learn, or record experiences/lessons, "
    "you MUST call `learn_experience` at least once before claiming success. "
    "Do not say experiences were updated unless the tool call has completed."
)


LEGACY_THINK_MODE_SYSTEM_DIRECTIVE = (
    "THINK MODE (COMPLEX TASKS): "
    "For complex or multi-step tasks, first create a concise execution plan, "
    "then execute tools in a deliberate sequence, validating outputs after each major step. "
    "When useful, verify assumptions with quick checks before making irreversible changes. "
    "Prioritize correctness and completeness over speed."
)


LEGACY_GUI_PERCEPTION_DIRECTIVE = (
    "GUI INTERACTION PROTOCOL (MANDATORY) - READ CAREFULLY:\n"
    "1. THINK BEFORE YOU ACT: You are operating a real graphical user interface. You cannot see it natively, so you rely on tools. NEVER hallucinate elements or coordinates.\n"
    "2. PERCEIVE FIRST: You MUST call `gui_analyze_screen` BEFORE making any decisions. Read the returned JSON carefully to understand the screen state (windows, elements, coordinates).\n"
    "3. TARGET BY EXACT TEXT: ALWAYS use `gui_find_element` or `gui_click_element` with the EXACT text from your analysis. Do NOT use `gui_mouse_move`/`gui_mouse_click` with raw coordinates unless absolutely necessary.\n"
    "4. VERIFY ACTIONS: After every action, use `gui_observe_transition` or `gui_analyze_screen` again to confirm the action succeeded before proceeding to the next step.\n"
    "5. ADAPT TO FAILURE: If an element is 'not found', DO NOT GUESS. Read the 'visible_elements' list returned by the tool. If the element is not there, it might be off-screen (use `gui_scroll_screen`) or the app might be loading (wait and retry).\n"
    "6. INTELLIGENT SEQUENCING: For multi-step tasks, form a plan. If you open an app, wait for it to appear in the active windows before trying to click inside it."
)


def _load_mode_directive(template_name: str, fallback: str) -> str:
    from_template = _load_prompt_template(template_name)
    return from_template if from_template else fallback


SELF_UPGRADE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "self_upgrade", LEGACY_SELF_UPGRADE_SYSTEM_DIRECTIVE
)
EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "experience", LEGACY_EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE
)
THINK_MODE_SYSTEM_DIRECTIVE = _load_mode_directive(
    "think", LEGACY_THINK_MODE_SYSTEM_DIRECTIVE
)
GUI_PERCEPTION_DIRECTIVE = LEGACY_GUI_PERCEPTION_DIRECTIVE


def _matches_intent(msg: str, triggers: list, negations: list = None) -> bool:
    if not msg:
        return False
    msg_lower = msg.lower()
    if negations is None:
        negations = ["don't", "do not", "never", "stop", "no", "avoid"]
    
    for trigger in triggers:
        idx = msg_lower.find(trigger)
        if idx != -1:
            # Check for negations appearing shortly before the trigger
            prefix = msg_lower[max(0, idx - 20):idx]
            if any(n in prefix for n in negations):
                continue
            return True
    return False

def _is_complex_task_prompt(user_msg: Any) -> bool:
    text = _get_text_content(user_msg).lower()
    if not text:
        return False

    multi_step_markers = ["1.", "2.", "first", "second", "then", "after that"]
    complex_keywords = [
        "architecture", "refactor", "migrate", "integrate", "multi-step", 
        "pipeline", "end-to-end", "optimize", "performance", "debug", 
        "deploy", "production", "comprehensive", "deep"
    ]

    if _matches_intent(text, complex_keywords):
        return True
    if sum(1 for m in multi_step_markers if m in text) >= 2:
        return True
    if len(text.split()) >= 40:
        return True
    return False

def _is_gui_interaction_request(user_msg: Any) -> bool:
    """Detect if the user wants to interact with the GUI / screen."""
    text = _get_text_content(user_msg)
    triggers = [
        "screen", "click", "mouse", "gui", "desktop", "window", 
        "screenshot", "type in", "open app", "open application", 
        "what's on", "what is on", "look at", "see my", "scroll", 
        "keyboard", "press", "menu", "button", "display", "monitor", "cursor"
    ]
    return _matches_intent(text, triggers)

def _is_self_upgrade_request(user_msg: Any) -> bool:
    text = _get_text_content(user_msg)
    triggers = [
        "new feature for yourself", "new feature for itself", "improve yourself", 
        "upgrade yourself", "self-improving", "add capability to yourself", 
        "write new feature for yourself", "write new feature for itself"
    ]
    return _matches_intent(text, triggers)

def _is_experience_update_request(user_msg: Any) -> bool:
    text = _get_text_content(user_msg)
    triggers = [
        "update your experiences", "update experiences", "record this experience", 
        "learn from this", "remember this lesson", "add this to your experiences"
    ]
    return _matches_intent(text, triggers)


def _inject_system_directive(session: Session, directive: str) -> None:
    if (
        not session.message_history
        or session.message_history[0].get("role") != "system"
    ):
        return
    content = session.message_history[0].get("content", "")
    if directive not in content:
        session.message_history[0]["content"] = content + "\n\n" + directive
        # System prompt content changed; sanitize output may differ.
        session.mark_dirty()


def _extract_memory_lines(results: Any, limit: int = 6) -> List[str]:
    if isinstance(results, dict):
        results = results.get("results", [])
    if not isinstance(results, list):
        results = [results]

    lines: List[str] = []
    for item in results:
        if isinstance(item, dict):
            text = item.get("memory") or item.get("text") or str(item)
        else:
            text = str(item)
        text = " ".join(text.split())
        if text and text not in lines:
            lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def _derive_identity_hints(memory_lines: List[str]) -> List[str]:
    hints = []
    for line in memory_lines:
        lower = line.lower()
        if "assistant:" in lower:
            lower = lower.split("assistant:")[0]
            
        if "name is " in lower:
            idx = lower.find("name is ")
            value = line[idx + len("name is ") :].split()[0].strip(" .:-")
            if value:
                hints.append(f"User name: {value}")
                break
        elif "i am " in lower:
            idx = lower.find("i am ")
            value = line[idx + len("i am ") :].split()[0].strip(" .:-")
            if value and value not in ["a", "an", "the", "not", "just", "only"]:
                hints.append(f"User name: {value}")
                break
    return hints


def _derive_basic_facts(memory_lines: List[str], max_facts: int = 6) -> List[str]:
    facts: List[str] = []
    seen = set()

    def add_fact(value: str) -> None:
        cleaned = " ".join(value.split()).strip(" -\t\n")
        if not cleaned:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append(cleaned)

    # High-priority identity fact (name)
    for line in memory_lines:
        match = re.search(
            r"\bname is\s+([a-zA-Z][a-zA-Z0-9 _'\-]{0,50})", line, flags=re.IGNORECASE
        )
        if match:
            add_fact(f"User name: {match.group(1).strip(' .:-')}")
            break

    # Other compact preference/tooling facts
    for line in memory_lines:
        lower = line.lower().strip()
        if len(facts) >= max_facts:
            break
        if lower.startswith("uses "):
            add_fact(line)
            continue
        if lower.startswith("prefers "):
            add_fact(line)
            continue
        if lower.startswith("wants ") and len(line) <= 140:
            add_fact(line)

    return facts[:max_facts]


def extract_auto_basic_facts(system_prompt_content: str) -> List[str]:
    start = system_prompt_content.find(AUTO_FACTS_START)
    if start == -1:
        return []
    end = system_prompt_content.find(AUTO_FACTS_END, start)
    if end == -1:
        return []

    block = system_prompt_content[start + len(AUTO_FACTS_START) : end]
    facts: List[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        facts.append(line)
    return facts


def _fetch_all_memories(memory_service: Any, user_id: int) -> Any:
    """Single point of access for `memory_service.get_all`. Used by both
    `_sync_basic_facts_into_system_prompt` and `_build_memory_context` so a
    given turn pays the (potentially network/embedding) cost at most once.
    Returns an empty list on error.
    """
    if not memory_service:
        return []
    try:
        # mem0 v2.0.0 requires entity IDs in a filters dict
        return memory_service.get_all(filters={"user_id": str(user_id)})
    except Exception:
        return []


def _sync_basic_facts_into_system_prompt(
    session: Session,
    memory_service: Any,
    *,
    all_results: Any = None,
) -> None:
    if not memory_service:
        return
    if (
        not session.message_history
        or session.message_history[0].get("role") != "system"
    ):
        return

    if all_results is None:
        all_results = _fetch_all_memories(memory_service, session.user_id)

    memory_lines = _extract_memory_lines(all_results, limit=40)
    facts = _derive_basic_facts(memory_lines, max_facts=6)

    content = str(session.message_history[0].get("content") or "")
    facts_body = "\n".join(f"- {fact}" for fact in facts)
    updated = _replace_tag_block(
        content,
        AUTO_FACTS_START,
        AUTO_FACTS_END,
        facts_body,
    )
    if updated != content:
        session.message_history[0]["content"] = updated
        session.mark_dirty()


def _build_memory_context(
    memory_service: Any,
    user_id: int,
    user_msg: Any,
    *,
    all_results: Any = None,
) -> Optional[str]:
    text = _get_text_content(user_msg)
    if not memory_service or not text:
        return None

    from tools.yolo_memory import TieredMemoryEngine
    if isinstance(memory_service, TieredMemoryEngine):
        sections = []
        
        # 1. Working Memory (L1) - Short-term context
        working_mem = memory_service.working_memory_get(user_id)
        if working_mem:
            wm_str = "\n".join(f"- {k}: {v}" for k,v in working_mem.items())
            sections.append(f"### [L1] Working Memory (Active Task Context)\n{wm_str}")
            
        # 2. Core Identity (L3 - High Importance)
        # Search relevant
        try:
            search_results = memory_service.search(text, filters={"user_id": str(user_id)}, limit=10)
        except Exception:
            search_results = []
            
        # Get all for identity hints
        if all_results is None:
            try:
                all_results = memory_service.get_all(filters={"user_id": str(user_id)})
            except Exception:
                all_results = []
                
        all_lines = _extract_memory_lines(all_results, limit=50)
        identity_hints = _derive_identity_hints(all_lines)
        
        if identity_hints:
            sections.append("### [L3] Core Identity & Preferences\n" + "\n".join(f"- {h}" for h in identity_hints))
            
        # 3. Relevant Semantic Knowledge (L3 / L2)
        relevant_lines = _extract_memory_lines(search_results, limit=10)
        # Filter out lines already in identity hints
        unique_relevant = [line for line in relevant_lines if line not in (identity_hints or [])]
        if unique_relevant:
            sections.append("### [L3] Relevant Semantic Knowledge\n" + "\n".join(f"- {line}" for line in unique_relevant))
            
        # 4. Behavioral Patterns (L4) — via public API
        if hasattr(memory_service, 'get_patterns'):
            try:
                patterns = memory_service.get_patterns(user_id, limit=5)
                if patterns:
                    sections.append("### [L4] Long-term Behavioral Patterns\n" + "\n".join(f"- {p}" for p in patterns))
            except Exception:
                pass
            
        if sections:
            return "[TIERED_MEMORY_CONTEXT]\n" + "\n\n".join(sections) + "\n[/TIERED_MEMORY_CONTEXT]"
        return None

    # Legacy mem0 logic
    if not user_msg:
        return None

    try:
        # mem0 v2.0.0 requires entity IDs in a filters dict
        search_results = memory_service.search(
            user_msg, filters={"user_id": str(user_id)}, limit=8
        )
    except Exception:
        search_results = []

    if all_results is None:
        all_results = _fetch_all_memories(memory_service, user_id)

    relevant_lines = _extract_memory_lines(search_results, limit=6)
    all_lines = _extract_memory_lines(all_results, limit=20)
    identity_hints = _derive_identity_hints(all_lines)

    sections: List[str] = []
    if identity_hints:
        sections.append(
            "Identity hints:\n" + "\n".join(f"- {h}" for h in identity_hints)
        )
    if relevant_lines:
        sections.append(
            "Relevant long-term memories:\n"
            + "\n".join(f"- {line}" for line in relevant_lines)
        )

    if not sections:
        return None

    return "[MEMORY_CONTEXT]\n" + "\n\n".join(sections)


def _repo_has_tests() -> bool:
    """Detect whether the repo has a test suite.

    Performance: result is cached for the process lifetime. Cheap checks
    (top-level `tests/` or `test/` dir) short-circuit. Only when those are
    absent do we fall back to a bounded walk that skips heavy directories
    like `node_modules`, `.venv`, etc. The walk is also depth-limited to
    avoid scanning thousands of files in vendored trees.
    """
    global _REPO_HAS_TESTS_CACHE
    if _REPO_HAS_TESTS_CACHE is not None:
        return _REPO_HAS_TESTS_CACHE

    root = Path.cwd()
    if (root / "tests").is_dir() or (root / "test").is_dir():
        _REPO_HAS_TESTS_CACHE = True
        return True

    skip_dirs = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "browser_profile",
        "artifacts",
    }

    # Depth-limited walk: tests are conventionally near the project root.
    max_depth = 3
    root_str = str(root)
    for base, dirs, files in os.walk(root):
        rel_depth = base[len(root_str) :].count(os.sep)
        if rel_depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for name in files:
            lower = name.lower()
            if (lower.startswith("test_") and lower.endswith(".py")) or lower.endswith(
                "_test.py"
            ):
                _REPO_HAS_TESTS_CACHE = True
                return True

    _REPO_HAS_TESTS_CACHE = False
    return False


# Performance: precompute at import so the first self-upgrade request
# does not pay the filesystem-walk cost inside the async hot path.
try:
    _repo_has_tests()
except Exception:
    pass


def _collect_turn_tool_names(history: List[Dict[str, Any]], start_idx: int) -> set[str]:
    names = set()
    for msg in history[start_idx:]:
        if msg.get("role") == "tool":
            name = msg.get("name")
            if name:
                names.add(name)
    return names


def _collect_run_bash_commands(
    history: List[Dict[str, Any]], start_idx: int
) -> List[str]:
    commands: List[str] = []
    for msg in history[start_idx:]:
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name")
            if fn != "run_bash":
                continue
            raw_args = (tc.get("function") or {}).get("arguments", "{}")
            try:
                parsed = json.loads(raw_args)
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                cmd = parsed.get("command")
                if isinstance(cmd, str) and cmd.strip():
                    commands.append(cmd.strip())
    return commands


def _missing_self_upgrade_phases(
    tool_names: set[str],
    run_bash_commands: Optional[List[str]] = None,
    require_pytest: bool = False,
) -> List[str]:
    research_tools = {
        "web_search",
        "browse_url",
        "browser_navigate",
        "browser_extract_text",
        "browser_extract_links",
        "mcp_list_tools",
        "mcp_run_tool",
    }
    implement_tools = {"write_file", "edit_file", "move_file", "copy_file", "make_dir"}
    evolve_tools = {
        "learn_experience",
        "archive_proactive_memory",
        "self_upgrade_summary",
        "optimize_skill",
        "develop_new_skill",
    }

    missing = []
    if not (tool_names & research_tools):
        missing.append("research")
    if not (tool_names & implement_tools):
        missing.append("implementation")
    if "run_bash" not in tool_names:
        missing.append("validation")
    elif require_pytest:
        commands = run_bash_commands or []
        has_pytest = any("pytest" in c.lower() for c in commands)
        if not has_pytest:
            missing.append("validation_pytest")
    if not (tool_names & evolve_tools):
        missing.append("evolution_update")
    return missing


class PendingConfirmationError(Exception):
    def __init__(self, action: str, path: str, tool_call_id: str, tool_args: dict):
        self.action = action
        self.path = path
        self.tool_call_id = tool_call_id
        self.tool_args = tool_args
        super().__init__(f"Pending confirmation for {action}")


def log_agent(user_id: int, tag: str, message: Any, color: str = Fore.CYAN):
    text = _get_text_content(message)
    if VERBOSE:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{Fore.WHITE}[{user_id}] [{ts}] {color}{Style.BRIGHT}{tag}{Style.NORMAL} {text}"
        )
    
    # Also log to audit file for TUI visibility
    from tools.base import audit_log
    audit_log("agent", {"user_id": user_id}, tag, text)


LEGACY_BASE_SYSTEM_PROMPT = (
    "You are Yolo, an elite autonomous system controller and expert software engineer. "
    "You possess intelligence on par with or exceeding the most advanced AI models in the world.\n\n"
    "You operate with a persistent identity and long-term memory. You can evolve through self-upgrade protocols and experience-based learning.\n\n"
    "CORE PRINCIPLES:\n"
    "1. Deep Reasoning: Always think step-by-step. Analyze problems systematically before generating solutions.\n"
    "2. Expert Execution: Write clean, idiomatic, and highly optimized code. Anticipate edge cases and handle errors gracefully.\n"
    "3. Adaptive Self-Correction: If a tool fails or an assumption is wrong, diagnose the root cause instead of blindly retrying.\n"
    "4. Precise Communication: Be concise but highly technical. Technical identifiers MUST be in `backticks`.\n"
    "5. Complete Autonomy: Take ownership of tasks from end-to-end. Do not ask for user permission unless absolutely necessary.\n\n"
    "BEHAVIORAL GUIDELINES (MANDATORY):\n"
    "• SEARCH-FIRST: For any factual question about the present-day world (roles, prices, laws, current status), you MUST use `web_search` before answering. Do not rely on training data for time-sensitive information.\n"
    "• TONE & FORMATTING: Use a warm, constructive tone. Respond in natural prose and paragraphs. Avoid over-formatting with headers, bold text, or bullet points unless essential or explicitly requested. Keep responses brief and focused.\n"
    "• COPYRIGHT COMPLIANCE: Paraphrase search results in your own voice. NEVER quote more than 15 words from a single source. Limit to ONE quote per source; once quoted, a source is CLOSED for further quotation. NEVER reproduce lyrics, poems, or article paragraphs.\n"
    "• NO VOICE NOTES: Never use `<antml:voice_note>` tags in your output.\n"
    "• EVENHANDEDNESS: Stay neutral on political/ethical debates. Provide balanced overviews of opposing views rather than personal opinions.\n"
    "• USER WELLBEING: Handle sensitive topics with care. Avoid encouraging self-destructive behaviors or reinforcing detachment from reality.\n\n"
    "Embrace your role as a top-tier cognitive engine."
)


LEGACY_BACKGROUND_SYSTEM_PROMPT = (
    "You are Yolo running a detached background mission. "
    "Do the task directly and DO NOT call `run_background_mission` again. "
    "If a tool needs user confirmation, skip that action and continue with safe alternatives. "
    "Technical identifiers MUST be in `backticks`."
)


def _build_template_driven_system_prompt(profile: Optional[str] = None) -> str:
    resolved_profile = _resolve_prompt_profile(profile)
    template_name = "base_compact" if resolved_profile == "compact" else "base"
    template = _load_prompt_template(template_name)
    if not template:
        template = (
            LEGACY_BASE_SYSTEM_PROMPT
            + "\n\nAuto Basic Facts\n"
            + AUTO_FACTS_START
            + "\n{{basic_facts}}\n"
            + AUTO_FACTS_END
        )
    return _render_prompt_template(template, basic_facts=[], identity_hints=[])


def get_initial_messages(profile: Optional[str] = None):
    if not _use_unified_prompt_architecture():
        return [{"role": "system", "content": LEGACY_BASE_SYSTEM_PROMPT}]
    return [{"role": "system", "content": _build_template_driven_system_prompt(profile)}]


def get_background_initial_messages() -> List[Dict[str, str]]:
    if not _use_unified_prompt_architecture():
        return [{"role": "system", "content": LEGACY_BACKGROUND_SYSTEM_PROMPT}]

    template = _load_prompt_template("background")
    content = template if template else LEGACY_BACKGROUND_SYSTEM_PROMPT
    return [{"role": "system", "content": content}]


def _merge_memory_context_into_system_prompt(
    session: Session,
    memory_context: Optional[str],
) -> None:
    if not session.message_history:
        session.message_history = get_initial_messages()

    if session.message_history[0].get("role") != "system":
        session.message_history.insert(0, get_initial_messages()[0])
        session.mark_dirty()

    base_content = str(session.message_history[0].get("content") or "")
    
    # Strip out any legacy hardcoded empty identity hints to prevent conflicts with the injected memory context
    base_content = base_content.replace("### Identity Hints\n- (none yet)", "").strip()
    
    payload = _extract_memory_context_payload(memory_context or "")
    merged = _replace_tag_block(
        base_content,
        MEMORY_CONTEXT_TRANSIENT_START,
        MEMORY_CONTEXT_TRANSIENT_END,
        payload,
    )
    if merged != str(session.message_history[0].get("content") or ""):
        session.message_history[0]["content"] = merged
        session.mark_dirty()


def _normalize_single_system_message(session: Session) -> None:
    if not session.message_history:
        return

    changed = False
    if session.message_history[0].get("role") != "system":
        session.message_history = get_initial_messages() + session.message_history
        changed = True

    primary = session.message_history[0]
    primary_content = str(primary.get("content") or "")
    memory_payloads: List[str] = []
    legacy_appendices: List[str] = []
    normalized: List[Dict[str, Any]] = [primary]

    for msg in session.message_history[1:]:
        if msg.get("role") != "system":
            normalized.append(msg)
            continue

        changed = True
        content = str(msg.get("content") or "").strip()
        if not content:
            continue
        if content.startswith("[MEMORY_CONTEXT]"):
            payload = _extract_memory_context_payload(content)
            if payload:
                memory_payloads.append(payload)
            continue
        if content.startswith("[CONVERSATION_SUMMARY]"):
            normalized.append({"role": "assistant", "content": content})
            continue
        legacy_appendices.append(content)

    merged = primary_content
    if memory_payloads:
        # If we found extra memory payloads in subsequent system messages, replace the existing one
        merged = _replace_tag_block(
            merged,
            MEMORY_CONTEXT_TRANSIENT_START,
            MEMORY_CONTEXT_TRANSIENT_END,
            "\n\n".join(memory_payloads),
        )
    
    if legacy_appendices:
        merged = _replace_tag_block(
            merged,
            LEGACY_APPENDIX_START,
            LEGACY_APPENDIX_END,
            "\n\n".join(legacy_appendices),
        )

    if merged != primary_content:
        primary["content"] = merged
        changed = True

    if changed:
        session.message_history = normalized
        session.mark_dirty()


def _extract_tool_path(args: dict) -> str:
    for key in ("path", "src", "dest", "command", "session_id"):
        value = args.get(key)
        if value:
            return str(value)
    return "(unknown path)"


def _is_destructive_or_sensitive_tool(func_name: str) -> bool:
    destructive = {
        "write_file",
        "edit_file",
        "delete_file",
        "move_file",
        "copy_file",
        "run_bash",
        "terminal_interactive_run",
        "terminal_start",
        "terminal_send",
        "terminal_stop",
        "memory_wipe",
        "cancel_scheduled_task",
        "optimize_skill",
        "update_user_identity",
        "git_commit",
        "git_branch",
    }
    return func_name in destructive


def _is_out_of_scope(args: dict) -> bool:
    cwd = Path.cwd().resolve(strict=False)
    for key in ("path", "src", "dest"):
        value = args.get(key)
        if not value:
            continue
        try:
            resolved = Path(str(value)).expanduser().resolve(strict=False)
        except Exception:
            return True

        try:
            resolved.relative_to(cwd)
        except ValueError:
            return True
    return False



__all__ = ["PendingConfirmationError", 'PROMPTS_DIR', '_is_small_model_name', '_use_unified_prompt_architecture', '_resolve_prompt_profile', '_load_prompt_template', '_load_identity_profile', '_render_prompt_template', '_strip_tag_block', '_replace_tag_block', '_extract_memory_context_payload', '_compact_history', 'LEGACY_SELF_UPGRADE_SYSTEM_DIRECTIVE', 'LEGACY_EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE', 'LEGACY_THINK_MODE_SYSTEM_DIRECTIVE', 'LEGACY_GUI_PERCEPTION_DIRECTIVE', '_load_mode_directive', 'SELF_UPGRADE_SYSTEM_DIRECTIVE', 'EXPERIENCE_UPDATE_SYSTEM_DIRECTIVE', 'THINK_MODE_SYSTEM_DIRECTIVE', 'GUI_PERCEPTION_DIRECTIVE', '_matches_intent', '_is_complex_task_prompt', '_is_gui_interaction_request', '_is_self_upgrade_request', '_is_experience_update_request', '_inject_system_directive', '_extract_memory_lines', '_derive_identity_hints', '_derive_basic_facts', 'extract_auto_basic_facts', '_fetch_all_memories', '_sync_basic_facts_into_system_prompt', '_build_memory_context', '_repo_has_tests', '_collect_turn_tool_names', '_collect_run_bash_commands', '_missing_self_upgrade_phases', 'log_agent', 'LEGACY_BASE_SYSTEM_PROMPT', 'LEGACY_BACKGROUND_SYSTEM_PROMPT', '_build_template_driven_system_prompt', 'get_initial_messages', 'get_background_initial_messages', '_merge_memory_context_into_system_prompt', '_normalize_single_system_message', '_extract_tool_path', '_is_destructive_or_sensitive_tool', '_is_out_of_scope']
