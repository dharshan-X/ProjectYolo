import datetime
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Disable mem0 telemetry to prevent local qdrant concurrent access errors (migrations_qdrant lock)
os.environ["MEM0_TELEMETRY"] = "false"

# Global Yolo Paths
YOLO_HOME = (
    Path(os.getenv("YOLO_HOME", str(Path.home() / ".yolo"))).expanduser().resolve()
)
YOLO_SKILLS = YOLO_HOME / "skills"
YOLO_BROWSER_PROFILE = YOLO_HOME / "browser_profile"
YOLO_MISSION_FILE = YOLO_HOME / ".yolo_mission"
YOLO_RESEARCH_FILE = YOLO_HOME / ".yolo_research_state"
YOLO_LOG_FILE = YOLO_HOME / "agent_log.txt"

# Local Paths (for deliverables)
YOLO_ARTIFACTS = Path(os.getenv("YOLO_ARTIFACTS_DIR", "artifacts")).expanduser()

# Ensure core system directories exist
for directory in [YOLO_HOME, YOLO_SKILLS, YOLO_BROWSER_PROFILE, YOLO_ARTIFACTS]:
    directory.mkdir(parents=True, exist_ok=True)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_and_verify_path(
    target_path: Union[str, Path], confirm_func: Optional[Callable] = None
) -> Path:
    """
    Resolve path and verify it stays within the current working directory.
    If outside, ask for permission via confirm_func.
    Always rejects sensitive OS prefixes.
    """
    raw_path = str(target_path)
    if "\x00" in raw_path:
        raise ValueError("Invalid path: null byte detected")

    cwd = Path.cwd().resolve()
    try:
        # Resolve path without requiring it to exist
        resolved = Path(raw_path).expanduser().resolve(strict=False)
    except Exception as e:
        raise ValueError(f"Invalid path: {e}") from e

    # Sensitive OS Prefixes (Hard Block)
    if os.name == "nt":
        sensitive_prefixes = [
            Path("C:/Windows"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            Path("C:/Users/Public"),
            Path("C:/Windows/System32"),
        ]
    else:
        sensitive_prefixes = [
            Path("/etc"),
            Path("/sys"),
            Path("/proc"),
            Path("/var"),
            Path("/root"),
            Path("/boot"),
            Path("/dev"),
        ]

    for prefix in sensitive_prefixes:
        is_sensitive = False
        try:
            if resolved == prefix or _is_relative_to(resolved, prefix):
                is_sensitive = True
        except Exception:
            # Handle cases where path comparison might fail due to drive mismatches or other OS quirks
            continue
            
        if is_sensitive:
            raise PermissionError(
                f"CRITICAL ACCESS DENIED: Path '{target_path}' is a sensitive system directory and is permanently blocked for security."
            )

    # CWD Sandboxing (Soft Block with Confirmation)
    if not _is_relative_to(resolved, cwd):
        if confirm_func and confirm_func("access out-of-scope path", str(resolved)):
            return resolved
        raise PermissionError(
            f"Access denied: Path '{target_path}' is outside the allowed workspace. "
            "Permission was not granted to exit the sandbox."
        )

    return resolved


def audit_log(tool: str, args: Dict[str, Any], status: str, detail: str = ""):
    """Append a structured log entry to the global agent_log.txt."""
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "tool": tool,
        "args": args,
        "status": status,
        "detail": detail,
    }
    try:
        with open(YOLO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        import sys
        sys.stderr.write(f"Failed to write audit log: {e}\n")


def format_log_line(line: str) -> str:
    """Prettify a JSON log line for display."""
    try:
        data = json.loads(line)
        ts = data.get("timestamp", "")
        if ts:
            ts = ts.split("T")[-1][:8]  # Just the time HH:MM:SS
        
        tool = data.get("tool", "system")
        status = data.get("status", "info")
        detail = data.get("detail", "")
        
        color = "green" if status == "success" else "red" if status == "error" else "yellow"
        
        # Textual-compatible markup
        return f"[[cyan]{ts}[/cyan]] [[b]{tool}[/b]] [{color}]{status}[/{color}] {detail}"
    except Exception:
        return line


def get_mem0_config():
    """
    Returns the standardized configuration for Mem0.
    Note: Mem0 requires an embedding model. If using a non-OpenAI LLM provider
    like Anthropic, you still need OPENAI_API_KEY for embeddings unless you
    configure a local/compatible embedding endpoint via OPENAI_BASE_URL.
    """
    from llm_router import load_llm_config
    llm_cfg = load_llm_config()

    api_key = os.getenv("OPENAI_API_KEY") or llm_cfg.api_key
    base_url = os.getenv("OPENAI_BASE_URL") or (llm_cfg.base_url if llm_cfg.provider in ["openai", "compatible"] else "https://api.openai.com/v1")
    
    llm_provider = llm_cfg.provider if llm_cfg.provider in ["openai", "anthropic", "openrouter"] else "openai"
    llm_config_dict = {"api_key": llm_cfg.api_key, "model": llm_cfg.model}
    if llm_cfg.base_url:
        if llm_provider == "openai":
            llm_config_dict["openai_base_url"] = llm_cfg.base_url
        else:
            llm_config_dict["base_url"] = llm_cfg.base_url

    # Adaptive Embedding Model for local setups
    if "4141" in base_url:
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-ada-002")
        embedding_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    elif api_key == "dummy" or "localhost" in base_url or "127.0.0.1" in base_url or (llm_cfg.provider == "anthropic" and not os.getenv("OPENAI_API_KEY")):
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "all-minilm")
        embedding_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "384"))
    else:
        embedding_model = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
        embedding_dim = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    memory_path = YOLO_HOME / "memory"
    memory_path.mkdir(exist_ok=True)

    return {
        "llm": {
            "provider": llm_provider,
            "config": llm_config_dict,
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "api_key": api_key,
                "openai_base_url": base_url,
                "model": embedding_model,
                "embedding_dims": embedding_dim,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "path": str(memory_path / "qdrant"),
                "embedding_model_dims": embedding_dim,
            },
        },
        "history_db_path": str(memory_path / "history.db"),
    }
