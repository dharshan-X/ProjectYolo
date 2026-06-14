from tools.registry import register_tool
import os
import datetime
from pathlib import Path
from tools.base import YOLO_ARTIFACTS, audit_log

ARTIFACTS_DIR = YOLO_ARTIFACTS


@register_tool()
def create_artifact(name: str, content: str, file_type: str = "md") -> str:
    """Create a persistent, high-quality deliverable in the artifacts directory."""
    try:
        # Ensure the artifacts directory exists
        base_path = Path(ARTIFACTS_DIR)
        base_path.mkdir(exist_ok=True)

        # Sanitize name and type to prevent path traversal
        safe_name = "".join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c in ("_", "-"))
        if not safe_name: safe_name = "artifact"
        safe_type = "".join(c for c in str(file_type) if c.isalnum())
        if not safe_type: safe_type = "md"
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_name}_{timestamp}.{safe_type}"
        file_path = base_path / filename

        # Write the content
        file_path.write_text(content, encoding="utf-8")

        audit_log("create_artifact", {"name": name, "file": filename}, "success")
        return f"Artifact created successfully: `{filename}`. View it at `{file_path}`."
    except Exception as e:
        audit_log("create_artifact", {"name": name}, "error", str(e))
        return f"Error creating artifact: {e}"


@register_tool()
def list_artifacts() -> str:
    """List all deliverables currently stored in the artifacts directory."""
    try:
        base_path = Path(ARTIFACTS_DIR)
        if not base_path.exists() or not any(base_path.iterdir()):
            return "No artifacts have been generated yet."

        artifacts = []
        # Sort by modification time (newest first)
        for item in sorted(base_path.iterdir(), key=os.path.getmtime, reverse=True):
            if item.is_file():
                size = item.stat().st_size
                mtime = datetime.datetime.fromtimestamp(item.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
                artifacts.append(f"• `{item.name}` ({size} bytes, {mtime})")

        audit_log("list_artifacts", {}, "success")
        return "Generated Artifacts:\n" + "\n".join(artifacts)
    except Exception as e:
        audit_log("list_artifacts", {}, "error", str(e))
        return f"Error listing artifacts: {e}"


@register_tool()
def get_latest_artifact() -> str:
    """Return the newest artifact as a direct upload signal for Telegram."""
    try:
        base_path = Path(ARTIFACTS_DIR)
        if not base_path.exists():
            return "Error: Artifacts directory does not exist yet."

        files = [p for p in base_path.iterdir() if p.is_file()]
        if not files:
            return "Error: No artifacts available to send."

        latest = max(files, key=lambda p: p.stat().st_mtime)
        audit_log("get_latest_artifact", {"file": latest.name}, "success")
        return f"__SEND_FILE__:{latest.resolve()}"
    except Exception as e:
        audit_log("get_latest_artifact", {}, "error", str(e))
        return f"Error getting latest artifact: {e}"
