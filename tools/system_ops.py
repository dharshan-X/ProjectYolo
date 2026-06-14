from tools.registry import register_tool
import os
import re
import select
import shlex
import signal
import subprocess
import threading
import time
import uuid

from dataclasses import dataclass

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix platforms
    from typing import Any
    fcntl: Any = None  # type: ignore[no-redef]

from tools.settings import load_settings

from tools.base import audit_log, resolve_and_verify_path

# Ensure env is loaded for settings
load_settings()


def _get_int_env(name: str, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value:
        return default
    return value


LOCAL_TIMEOUT_SECONDS = _get_int_env("BASH_TIMEOUT_SECONDS", 300)
DOCKER_TIMEOUT_SECONDS = _get_int_env("DOCKER_BASH_TIMEOUT_SECONDS", 90)
MAX_OUTPUT_CHARS = _get_int_env("MAX_BASH_OUTPUT_CHARS", 30000)
TERMINAL_READ_WAIT_MS = _get_int_env("TERMINAL_READ_WAIT_MS", 120, min_value=0)


@dataclass
class _TerminalSession:
    session_id: str
    process: subprocess.Popen
    master_fd: int
    shell: str
    cwd: str
    created_at: float


_terminal_sessions: dict[str, _TerminalSession] = {}
_terminal_lock = threading.Lock()


# Regex to strip ONLY invisible control sequences while preserving printable content.
# This keeps ASCII art, box-drawing chars, tables, and color codes intact.
_CONTROL_RE = re.compile(
    r"""
    \x1b        # ESC character
    (?:         # followed by:
      \]        #   OSC sequences: ESC ] ... (BEL or ST)  — window titles, etc.
      [^\x07]*  #     payload
      (?:\x07|\x1b\\)  # terminated by BEL or ST
    |
      [()][AB012]  # Character set selection
    |
      [>=]      # Keypad modes
    |
      \#\d      # Line height
    )
    | \x0f      # SI (Shift In)
    | \x0e      # SO (Shift Out)
    """,
    re.VERBOSE,
)


def _process_carriage_returns(text: str) -> str:
    """Simulate carriage-return overwrites so the final visible line is preserved.

    Many CLI tools (progress bars, spinners) use \\r to rewrite a line in-place.
    Instead of stripping \\r blindly (which concatenates all rewrites), we keep
    only the *last* segment after the final \\r on each line.
    """
    out_lines: list[str] = []
    for line in text.split("\n"):
        if "\r" in line:
            # Take the last CR-delimited segment (what you'd actually see)
            segments = line.split("\r")
            visible = segments[-1] if segments[-1] else (segments[-2] if len(segments) > 1 else "")
            out_lines.append(visible)
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _clean_terminal_output(text: str) -> str:
    """Clean terminal output while preserving ASCII art, colors, and box-drawing characters."""
    # 1. Remove truly invisible control sequences (OSC, charset, keypad)
    cleaned = _CONTROL_RE.sub("", text)
    # 2. Process carriage returns (simulate overwrite, keep final visible text)
    cleaned = _process_carriage_returns(cleaned)
    # 3. Collapse excessive blank lines (common after stripping prompts)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _trim_output(text: str) -> str:
    text = _clean_terminal_output(text)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    trimmed = text[:MAX_OUTPUT_CHARS]
    return (
        trimmed
        + f"\n\n[OUTPUT TRUNCATED: showing first {MAX_OUTPUT_CHARS} characters of {len(text)} total]"
    )


def _set_nonblocking(fd: int) -> None:
    if fcntl is None:
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _read_from_fd(master_fd: int, max_chars: int) -> str:
    chunks: list[bytes] = []
    collected = 0

    while collected < max_chars:
        ready, _, _ = select.select([master_fd], [], [], 0)
        if not ready:
            break
        try:
            buf = os.read(master_fd, min(4096, max_chars - collected))
        except BlockingIOError:
            break
        except OSError:
            break

        if not buf:
            break
        chunks.append(buf)
        collected += len(buf)

    if not chunks:
        return ""
    return b"".join(chunks).decode("utf-8", errors="replace")


def _get_session(session_id: str) -> _TerminalSession:
    with _terminal_lock:
        sess = _terminal_sessions.get(session_id)
    if not sess:
        raise ValueError(f"Terminal session '{session_id}' not found.")
    return sess


@register_tool()
def terminal_start(shell: str = "", cwd: str = "") -> str:
    """Start a persistent interactive terminal session and return a session ID."""
    if os.name == "nt":
        return "Error: interactive terminal sessions are currently supported on Unix-like systems only."

    try:
        import pty

        # Default to /bin/bash for reliable PTY interaction.
        # Fish and exotic shells have PTY ownership issues when spawned
        # programmatically. Users can still pass shell="fish" explicitly.
        shell_bin = shell.strip() or "/bin/bash"
        target_cwd = (
            str(resolve_and_verify_path(cwd)) if cwd and cwd.strip() else os.getcwd()
        )
        shell_parts = shlex.split(shell_bin)
        if not shell_parts:
            return "Error: Invalid shell command."

        # Build a clean environment — keep TERM=xterm so programs produce
        # full output (ASCII art, box-drawing, tables) instead of degraded plain text.
        clean_env = os.environ.copy()
        clean_env["TERM"] = "xterm-256color"
        clean_env["PS1"] = "$ "
        clean_env["PS2"] = "> "
        clean_env.pop("PROMPT_COMMAND", None)

        # Determine shell-specific flags to suppress rc files and greeting
        shell_base = os.path.basename(shell_parts[0])
        shell_args = list(shell_parts)
        if shell_base in ("bash", "sh"):
            shell_args += ["--norc", "--noprofile"]
        elif shell_base == "zsh":
            clean_env["ZDOTDIR"] = "/nonexistent"
            shell_args += ["--no-rcs", "--no-globalrcs"]
        elif shell_base == "fish":
            shell_args += ["--no-config"]

        master_fd, slave_fd = pty.openpty()

        proc = subprocess.Popen(
            shell_args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=target_cwd,
            env=clean_env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave_fd)
        _set_nonblocking(master_fd)

        session_id = str(uuid.uuid4())
        session = _TerminalSession(
            session_id=session_id,
            process=proc,
            master_fd=master_fd,
            shell=" ".join(shell_parts),
            cwd=target_cwd,
            created_at=time.time(),
        )

        with _terminal_lock:
            _terminal_sessions[session_id] = session

        time.sleep(max(0, TERMINAL_READ_WAIT_MS) / 1000.0)
        banner = _read_from_fd(master_fd, MAX_OUTPUT_CHARS)

        audit_log(
            "terminal_start",
            {"session_id": session_id, "shell": session.shell, "cwd": target_cwd},
            "success",
            f"PID: {proc.pid}",
        )

        if banner:
            banner = _trim_output(banner)
            return (
                f"Terminal session started. session_id={session_id}\n"
                f"shell={session.shell} cwd={target_cwd} pid={proc.pid}\n"
                f"[INITIAL_OUTPUT]\n{banner}"
            )

        return (
            f"Terminal session started. session_id={session_id}\n"
            f"shell={session.shell} cwd={target_cwd} pid={proc.pid}"
        )
    except Exception as e:
        audit_log("terminal_start", {"shell": shell, "cwd": cwd}, "error", str(e))
        return f"Error starting terminal session: {e}"


@register_tool()
def terminal_send(
    session_id: str,
    text: str,
    append_newline: bool = True,
    read_after_send: bool = True,
) -> str:
    """Send text to an interactive terminal session (like typing then Enter)."""
    try:
        session = _get_session(session_id)
        if session.process.poll() is not None:
            return (
                f"Session '{session_id}' has already exited with code {session.process.returncode}."
            )

        payload = text
        if append_newline:
            payload += "\n"

        os.write(session.master_fd, payload.encode("utf-8", errors="replace"))
        audit_log(
            "terminal_send",
            {"session_id": session_id, "text_len": len(text)},
            "success",
        )

        if not read_after_send:
            return f"Input sent to session '{session_id}'."

        time.sleep(max(0, TERMINAL_READ_WAIT_MS) / 1000.0)
        out = _read_from_fd(session.master_fd, MAX_OUTPUT_CHARS)
        if not out:
            return f"Input sent to session '{session_id}'. No immediate output."

        return _trim_output(out)
    except Exception as e:
        audit_log("terminal_send", {"session_id": session_id}, "error", str(e))
        return f"Error sending terminal input: {e}"


@register_tool()
def terminal_read(session_id: str, max_chars: int = MAX_OUTPUT_CHARS, wait_seconds: float = 0) -> str:
    """Read currently available output from a terminal session without sending input.
    
    If wait_seconds > 0, poll repeatedly until output appears or the timeout is reached.
    This is useful for slow commands (e.g. compilation, package install) where the agent
    needs to wait for the process to produce output before continuing.
    """
    try:
        session = _get_session(session_id)

        deadline = time.time() + max(0.0, wait_seconds)
        chunks: list[str] = []

        while True:
            piece = _read_from_fd(session.master_fd, max(1, max_chars))
            if piece:
                chunks.append(piece)
            # If we have output and no wait, or deadline passed, stop polling
            if chunks and wait_seconds <= 0:
                break
            if time.time() >= deadline:
                break
            # If process exited, grab any last output and stop
            if session.process.poll() is not None:
                final = _read_from_fd(session.master_fd, max(1, max_chars))
                if final:
                    chunks.append(final)
                break
            time.sleep(0.1)

        status = (
            "running"
            if session.process.poll() is None
            else f"exited({session.process.returncode})"
        )
        out = "".join(chunks)
        if not out:
            return f"No new output. Session '{session_id}' status={status}."

        return f"[status={status}]\n" + _trim_output(out)
    except Exception as e:
        audit_log("terminal_read", {"session_id": session_id}, "error", str(e))
        return f"Error reading terminal output: {e}"


@register_tool()
def terminal_list() -> str:
    """List all active terminal sessions with their status, shell, cwd, and age."""
    with _terminal_lock:
        sessions = list(_terminal_sessions.values())

    if not sessions:
        return "No active terminal sessions."

    lines = [f"Active terminal sessions ({len(sessions)}):"]
    for sess in sessions:
        alive = sess.process.poll() is None
        status = "running" if alive else f"exited({sess.process.returncode})"
        age = int(time.time() - sess.created_at)
        lines.append(
            f"  • {sess.session_id}  status={status}  shell={sess.shell}  "
            f"cwd={sess.cwd}  age={age}s  pid={sess.process.pid}"
        )
    return "\n".join(lines)


@register_tool()
def terminal_stop(session_id: str, force: bool = False) -> str:
    """Stop and clean up an interactive terminal session."""
    try:
        with _terminal_lock:
            session = _terminal_sessions.pop(session_id, None)
        if not session:
            return f"Session '{session_id}' not found."

        proc = session.process
        if proc.poll() is None:
            try:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(proc.pid, sig)
            except Exception:
                if force:
                    proc.kill()
                else:
                    proc.terminate()

            try:
                proc.wait(timeout=2 if force else 5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

        try:
            os.close(session.master_fd)
        except OSError:
            pass

        audit_log(
            "terminal_stop",
            {"session_id": session_id, "force": force},
            "success",
            f"Exit code: {proc.returncode}",
        )
        return f"Terminal session '{session_id}' stopped with exit code {proc.returncode}."
    except Exception as e:
        audit_log("terminal_stop", {"session_id": session_id}, "error", str(e))
        return f"Error stopping terminal session: {e}"


def _parse_session_id(start_output: str) -> str:
    marker = "session_id="
    idx = start_output.find(marker)
    if idx < 0:
        return ""
    rest = start_output[idx + len(marker) :]
    token = rest.splitlines()[0].split()[0].strip()
    return token


@register_tool()
def terminal_interactive_run(
    command: str = "",
    inputs: list[str] | None = None,
    cwd: str = "",
    shell: str = "",
    stop_after: bool = True,
    force_stop: bool = False,
) -> str:
    """Run a full interactive terminal flow: start, send command/inputs, read output, optional stop."""
    session_id = ""
    transcript: list[str] = []

    try:
        start_output = terminal_start(shell=shell, cwd=cwd)
        transcript.append(f"[START]\n{start_output}")

        session_id = _parse_session_id(start_output)
        if not session_id:
            audit_log(
                "terminal_interactive_run",
                {"command": command, "cwd": cwd},
                "error",
                "Failed to parse session_id from terminal_start output",
            )
            return "\n\n".join(transcript)

        if command:
            cmd_output = terminal_send(
                session_id=session_id,
                text=command,
                append_newline=True,
                read_after_send=True,
            )
            transcript.append(f"[COMMAND]\n$ {command}\n{cmd_output}")

        for idx, user_input in enumerate(inputs or [], start=1):
            step_output = terminal_send(
                session_id=session_id,
                text=user_input,
                append_newline=True,
                read_after_send=True,
            )
            transcript.append(f"[INPUT {idx}]\n{user_input}\n{step_output}")

        final_read = terminal_read(session_id=session_id, wait_seconds=2)
        if not final_read.startswith("No new output"):
            transcript.append(f"[FINAL_READ]\n{final_read}")

        if stop_after:
            stop_output = terminal_stop(session_id=session_id, force=force_stop)
            transcript.append(f"[STOP]\n{stop_output}")

        audit_log(
            "terminal_interactive_run",
            {
                "session_id": session_id,
                "command": command,
                "inputs_count": len(inputs or []),
                "stop_after": stop_after,
            },
            "success",
        )
        return _trim_output("\n\n".join(transcript))
    except Exception as e:
        if session_id and stop_after:
            terminal_stop(session_id=session_id, force=True)
        audit_log(
            "terminal_interactive_run",
            {"session_id": session_id, "command": command, "cwd": cwd},
            "error",
            str(e),
        )
        transcript.append(f"Error in interactive run: {e}")
        return _trim_output("\n\n".join(transcript))


@register_tool()
def run_bash(command: str) -> str:
    """Execute a bash command either locally or in a Docker sandbox."""
    enabled = os.getenv("DOCKER_SANDBOX_ENABLED", "false").lower() == "true"
    image = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    if enabled:
        return run_bash_in_docker(command, image)
    else:
        return run_bash_locally(command)


def run_bash_locally(command: str) -> str:
    """Execute a command on the host system using the appropriate shell."""
    try:
        shell = ["cmd", "/c"] if os.name == "nt" else ["bash", "-c"]
        result = subprocess.run(
            shell + [command],
            capture_output=True,
            text=True,
            timeout=LOCAL_TIMEOUT_SECONDS,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        status = "success" if result.returncode == 0 else "error"
        audit_log(
            "run_bash_local",
            {"command": command},
            status,
            f"Exit code: {result.returncode}",
        )

        output = _trim_output(output)
        return (
            output
            if output
            else f"(Command executed with exit code {result.returncode}, no output)"
        )
    except subprocess.TimeoutExpired:
        audit_log("run_bash_local", {"command": command}, "error", "Timeout")
        return (
            f"Error: Command timed out after {LOCAL_TIMEOUT_SECONDS} seconds. "
            f"For long-running commands (npm install, git clone, docker build, compilation), "
            f"use `terminal_start` + `terminal_send` + `terminal_read(wait_seconds=N)` instead "
            f"to avoid timeouts and monitor progress."
        )
    except Exception as e:
        audit_log("run_bash_local", {"command": command}, "error", str(e))
        return f"{type(e).__name__}: {e}"


def run_bash_in_docker(command: str, image: str) -> str:
    """Execute a bash command inside a Docker container mounting the CWD."""
    try:
        cwd = os.getcwd()
        # docker run --rm -v CWD:/workspace -w /workspace IMAGE bash -c COMMAND
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cwd}:/workspace",
            "-w",
            "/workspace",
            image,
            "bash",
            "-c",
            command,
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        status = "success" if result.returncode == 0 else "error"
        audit_log(
            "run_bash_docker",
            {"command": command, "image": image},
            status,
            f"Exit code: {result.returncode}",
        )

        output = _trim_output(output)
        return (
            output
            if output
            else f"(Docker command executed with exit code {result.returncode}, no output)"
        )
    except subprocess.TimeoutExpired:
        audit_log("run_bash_docker", {"command": command}, "error", "Timeout")
        return (
            f"Error: Docker command timed out after {DOCKER_TIMEOUT_SECONDS} seconds."
        )
    except Exception as e:
        audit_log("run_bash_docker", {"command": command}, "error", str(e))
        return f"{type(e).__name__}: {e}"


@register_tool()
def adjust_rate_limiting(rpm_limit: int) -> str:
    """Adjust the LLM request rate limit (requests per minute). Set to 0 to disable."""
    try:
        from tools.settings import update_setting
        update_setting("LLM_RPM_LIMIT", str(rpm_limit))
        audit_log("adjust_rate_limiting", {"rpm_limit": rpm_limit}, "success", f"Rate limit set to {rpm_limit} RPM")
        return f"Successfully updated rate limit to {rpm_limit} requests per minute."
    except Exception as e:
        audit_log("adjust_rate_limiting", {"rpm_limit": rpm_limit}, "error", str(e))
        return f"Error: {e}"

