from tools.registry import register_tool
import datetime
import json
import os
import re
import shutil
from typing import Callable, Optional

from tools.base import audit_log, resolve_and_verify_path, _get_int_env


MAX_READ_CHARS = _get_int_env("MAX_FILE_READ_CHARS", 120000)


def _truncate_content(content: str, limit: int = MAX_READ_CHARS) -> str:
    if len(content) <= limit:
        return content
    return (
        content[:limit]
        + f"\n\n[TRUNCATED: showing first {limit} characters of {len(content)} total]"
    )


@register_tool()
def read_file(path: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.is_file():
            return f"Error: '{path}' is not a file."
        
        suffix = resolved.suffix.lower()
        if suffix in (".pdf", ".docx", ".pptx", ".xlsx", ".md"):
            from tools.document_parser import extract_text_from_file
            content = extract_text_from_file(resolved)
        else:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            content = _truncate_content(content)
        
        audit_log("read_file", {"path": path}, "success")
        return content
    except Exception as e:
        audit_log("read_file", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def write_file(path: str, content: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)


        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        audit_log("write_file", {"path": path}, "success")
        return f"Successfully wrote to '{path}'."
    except Exception as e:
        audit_log("write_file", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def edit_file(
    path: str, old_text: str, new_text: str, confirm_func: Optional[Callable] = None
) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.is_file():
            return f"Error: '{path}' is not a file."



        content = resolved.read_text(encoding="utf-8")
        occurrences = content.count(old_text)
        if occurrences == 0:
            return (
                f"Error: Could not find exact text match for replacement in '{path}'."
            )
        if occurrences > 1:
            return (
                f"Error: The text to replace appears {occurrences} times in '{path}'. "
                "Replacement would be ambiguous. Provide a longer, unique snippet "
                "(include surrounding context) so exactly one match is targeted."
            )

        new_content = content.replace(old_text, new_text, 1)
        resolved.write_text(new_content, encoding="utf-8")
        audit_log("edit_file", {"path": path}, "success")
        return f"Successfully edited '{path}'."
    except Exception as e:
        audit_log("edit_file", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def delete_file(path: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.exists():
            return f"Error: '{path}' does not exist."



        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        audit_log("delete_file", {"path": path}, "success")
        return f"Successfully deleted '{path}'."
    except Exception as e:
        audit_log("delete_file", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def copy_file(src: str, dest: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        s_resolved = resolve_and_verify_path(src, confirm_func)
        d_resolved = resolve_and_verify_path(dest, confirm_func)

        if not s_resolved.exists():
            return f"Error: Source '{src}' does not exist."



        d_resolved.parent.mkdir(parents=True, exist_ok=True)
        if s_resolved.is_dir():
            shutil.copytree(s_resolved, d_resolved, dirs_exist_ok=True)
        else:
            shutil.copy2(s_resolved, d_resolved)
        audit_log("copy_file", {"src": src, "dest": dest}, "success")
        return f"Successfully copied '{src}' to '{dest}'."
    except Exception as e:
        audit_log("copy_file", {"src": src, "dest": dest}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def move_file(src: str, dest: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        s_resolved = resolve_and_verify_path(src, confirm_func)
        d_resolved = resolve_and_verify_path(dest, confirm_func)

        if not s_resolved.exists():
            return f"Error: Source '{src}' does not exist."



        d_resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s_resolved), str(d_resolved))
        audit_log("move_file", {"src": src, "dest": dest}, "success")
        return f"Successfully moved '{src}' to '{dest}'."
    except Exception as e:
        audit_log("move_file", {"src": src, "dest": dest}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def list_dir(path: str = ".", confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.is_dir():
            return f"Error: '{path}' is not a directory."

        entries = []
        for item in resolved.iterdir():
            t = "DIR" if item.is_dir() else "FILE"
            entries.append(f"[{t}] {item.name}")

        audit_log("list_dir", {"path": path}, "success")
        return "\n".join(sorted(entries)) if entries else "(empty directory)"
    except Exception as e:
        audit_log("list_dir", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def make_dir(path: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        resolved.mkdir(parents=True, exist_ok=True)
        audit_log("make_dir", {"path": path}, "success")
        return f"Successfully created directory '{path}'."
    except Exception as e:
        audit_log("make_dir", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def file_info(path: str, confirm_func: Optional[Callable] = None) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.exists():
            return f"Error: '{path}' does not exist."

        stats = resolved.stat()
        info = {
            "size_bytes": stats.st_size,
            "last_modified": datetime.datetime.fromtimestamp(
                stats.st_mtime
            ).isoformat(),
        }

        if os.name == "posix":
            info["permissions"] = oct(stats.st_mode & 0o777)
        else:
            info["note"] = "Permissions field omitted (platform limitation: Windows)."

        audit_log("file_info", {"path": path}, "success")
        return json.dumps(info, indent=2)
    except Exception as e:
        audit_log("file_info", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def search_in_file(
    path: str, pattern: str, confirm_func: Optional[Callable] = None
) -> str:
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.is_file():
            return f"Error: '{path}' is not a file."

        matches = []
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex pattern '{pattern}': {e}"
        with resolved.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                if regex.search(line):
                    matches.append(f"Line {i}: {line.strip()}")

        audit_log("search_in_file", {"path": path, "pattern": pattern}, "success")
        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        audit_log("search_in_file", {"path": path, "pattern": pattern}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def send_to_telegram(path: str, confirm_func: Optional[Callable] = None) -> str:
    """Signal the bot to upload a file to the user."""
    try:
        resolved = resolve_and_verify_path(path, confirm_func)
        if not resolved.is_file():
            return f"Error: '{path}' is not a file."

        # We return a special prefix that the bot will catch
        audit_log("send_to_telegram", {"path": path}, "success")
        return f"__SEND_FILE__:{resolved}"
    except Exception as e:
        audit_log("send_to_telegram", {"path": path}, "error", str(e))
        return f"{type(e).__name__}: {e}"
