# Codebase Review: ProjectYolo

**Date:** 2026-07-11
**Scope:** 16 Python modules at the project root (`agent.py`, `bot.py`, `cli.py`, `server.py`, `session.py`, `tui.py`, `tui_widgets.py`, `worker.py`, `prompt_builder.py`, `llm_router.py`, `tool_dispatcher.py`, `error_classifier.py`, `whisper_local.py`, `discord_gateway.py`, `monitoring.py`, `health_server.py`), 30 modules under `tools/` (with focus on `base.py`, `file_ops.py`, `system_ops.py`, `mcp_manager.py`), and the 22-file `tests/` suite.
**Method:** Read entry points and routing layer end-to-end; traced three critical paths (TUI/Telegram message → LLM → tool → response, prompt construction, tool invocation with sandbox checks); grepped the test suite for the allow-list and destructive-tool protections to confirm coverage.

## Executive summary

- **Discord gateway is effectively unauthenticated** when `DISCORD_ALLOWED_USER_IDS` is empty — a single missing env var makes the bot accept messages from **any** Discord user. No test guards this. (`discord_gateway.py:22-27`)
- **`_run_with_history_sync` re-enters the agent with `memory_service=None`** (`tool_dispatcher.py:96`), and `resolve_confirmations` does the same (`agent.py:844`) — meaning the auto-memory path silently stops persisting after the first confirmation round.
- **Telegram/Discord ID allow-lists have no test coverage at all**; the only safety net on a public-facing bot is environment configuration, with no startup assertion that it's actually configured.
- **The `pending_confirmations` list is mutated across async boundaries in two places without full lock coverage** — `agent.resolve_confirmations` (`agent.py:794-815`) and `deny_confirmations` (`agent.py:847-878`) are called from inside session locks, but `_execute_unanswered_tool_calls` (`agent.py:218-332`) clears the list at the top of a turn before re-populating it; a concurrent message could observe an empty list in between.
- **The codebase is well-designed overall** — clear separation between router/dispatcher/agent, sandboxed filesystem operations, MCP subprocess isolation, structured audit logging, and a thoughtful destructive-tool gate. The findings below are real but represent a small fraction of the total surface area.

## Critical findings (P0 — fix immediately)

### P0-1. Discord gateway is unauthenticated when env var is empty

**What:** `_is_allowed_user` returns `True` for any user when the env var is missing/empty.

**Where:** `discord_gateway.py:22-27`
```python
def _is_allowed_user(user_id: int) -> bool:
    raw = os.getenv("DISCORD_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return True              # <-- open by default
    allowed = {int(v.strip()) for v in raw.split(",") if v.strip()}
    return user_id in allowed
```

**Impact:** A deployed Discord bot with the default `.env.example` template (`DISCORD_ALLOWED_USER_IDS=` is left blank) lets **every** Discord user issue commands, run `run_bash`, and trigger destructive tools. In yolo mode (which a malicious user could enable via `/mode yolo` if the bot doesn't have a UI restriction), this is a remote-shell-as-service. The bot **does not** even fail to start — it just silently accepts everyone. `tests/` has **zero** coverage of this function (verified by `grep -r "ALLOWED_USER_IDS" tests/` returning nothing).

**Confidence:** High — the code is unambiguous, the default env is empty, and the deny-by-default pattern is exactly inverted.

**Suggested fix:** Default to `False` and fail to start the gateway on empty config:
```python
if not raw:
    logger.error("DISCORD_ALLOWED_USER_IDS is empty — refusing to start Discord gateway.")
    raise RuntimeError(...)
```

### P0-2. Auto-memory persistence is broken after the first HITL confirmation round

**What:** Both `run_background_mission` (via `_run_with_history_sync` in `tool_dispatcher.py`) and `resolve_confirmations` (in `agent.py`) call `run_agent_turn` without the `memory_service` argument. `agent._finalize_or_request_more_work` (`agent.py:641-652`) is the only place `memory_service.add()` is called — so once memory is `None`, no further auto-memories are written.

**Where:** `tool_dispatcher.py:92-97`
```python
res = await run_agent_turn(
    objective,
    worker_session,
    signal_handler=wrapped_handler,
    memory_service=None    # <-- background workers never persist
)
```

And `agent.py:844`:
```python
# After resolving, run the agent turn again to process results
return await run_agent_turn(None, session, signal_handler=signal_handler)
```

The second call's `memory_service` is `None` (default) because `resolve_confirmations` doesn't accept or forward it. The user explicitly invoked with `memory_service=session_manager.memory` (e.g. `bot.py:862`), and it's silently dropped on the second invocation.

**Impact:** Background missions never persist memories. The whole point of a multi-step turn (HITL confirm → continue) is that the second half should remember, and it doesn't. This is silent data loss and a correctness bug in a feature the README advertises.

**Confidence:** High.

**Suggested fix:** `resolve_confirmations` should accept and forward `memory_service`; `_run_with_history_sync` should pass through the parent's `memory_service` from `parent_session` (or accept it explicitly via the `mission_coro` closure — which it does have access to).

### P0-3. Telegram `ALLOWED_USER_IDS` is not enforced if env var is missing

**What:** The Telegram path uses a **different pattern** than Discord: `ALLOWED_USER_IDS` is parsed at startup as a list, and an empty list means nothing matches in `auth_check`. The Telegram bot **does** refuse to start without a token (`bot.py:78-80`) but it does **not** refuse to start without `TELEGRAM_ALLOWED_USER_IDS`. The default `.env.example` ships it empty, and the consequence is that `ALLOWED_USER_IDS` becomes `[]` and every `auth_check` returns `False`, so every message is silently dropped — that part is safe by accident.

**But** if the operator adds a single ID like `"12345"`, then registers a second user as `"12345, 67890"`, and then **deletes** the env var to debug, the bot becomes "secure again" by accident. The semantic is implicit and unobservable. No test covers this.

**Where:** `bot.py:41-45` parses, `bot.py:310-316` checks.

**Impact:** Lower than P0-1 because the default behavior is "silently no one can use it" rather than "silently everyone can use it." But: a future refactor that flips the comparison (`user_id in ALLOWED_USER_IDS` → `if not user_id in ALLOWED_USER_IDS: return True`) would re-create P0-1 in the Telegram path. The contract should be explicit.

**Confidence:** Medium (the current code is "safe by accident" but the contract is implicit and brittle).

**Suggested fix:** Add a startup assertion alongside the token check:
```python
if not ALLOWED_USER_IDS:
    print(Fore.RED + "[ERROR] TELEGRAM_ALLOWED_USER_IDS is not set in .env.")
    sys.exit(1)
```

## High-priority findings (P1 — fix soon)

### P1-1. `run_bash` does not consult `_is_destructive_or_sensitive_tool` — but the gate relies on the implicit list

**What:** `run_bash` is in the explicit destructive set (`prompt_builder.py:1018`). The function looks like:
```python
@register_tool()
def run_bash(command: str) -> str:        # <-- no confirm_func
```

It accepts no `confirm_func`, and inside `tool_dispatcher.py` the gate that converts "destructive" → "pending confirmation" runs **before** the tool is called (good). But the tool itself has no second layer of safety: if a future refactor moves the gate or a new caller invokes `run_bash` directly (e.g. a worker bypasses the dispatcher), the tool will execute unconditionally.

**Where:** `tools/system_ops.py:504-512`

**Impact:** A latent footgun. The current `agent.py:271` gate is the only thing keeping this safe.

**Confidence:** Medium — depends on refactor risk.

**Suggested fix:** Add an internal `confirm_func` argument (for consistency with `file_ops`) and require it to be truthy at execution time.

### P1-2. `terminal_interactive_run` opens a real PTY on the host — no out-of-scope protection; inherits full env including secrets

**What:** `terminal_start` (`tools/system_ops.py:166-256`) calls `resolve_and_verify_path(cwd, confirm_func)` with `confirm_func=None`. So when an LLM passes a `cwd` outside the sandbox, the path is silently resolved and the shell starts there. There is **no** `_is_out_of_scope` check analogous to what `_is_out_of_scope` does for other tools (`prompt_builder.py:1038-1053`).

Compare: the `_is_out_of_scope` helper is **only** consulted inside `_execute_unanswered_tool_calls` in `agent.py` (line 270), which runs before the tool is dispatched. So this *is* gated, but the gate is one layer removed. If a future caller bypasses `_execute_unanswered_tool_calls` (e.g. the `run_background_mission` inner loop or a `run_bash` shell that exec's `terminal_start`), the safety is gone.

**Confidence:** Medium. The terminal also inherits the full environment, including `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `DISCORD_BOT_TOKEN` (verified at `tools/system_ops.py:187-191` — `clean_env = os.environ.copy()`). The PTY child process can `env | grep KEY`.

**Suggested fix:** Strip secrets from `clean_env` by default (with an explicit opt-in for terminals that need them), or scope env to a curated allowlist.

### P1-3. `pending_confirmations` mutations span the session lock and a tool-dispatcher re-entry

**What:** `agent._execute_unanswered_tool_calls` (`agent.py:218-332`) does this at the start of every turn:
```python
session.pending_confirmations = []   # line 238
```

This happens *inside* the agent loop, which is itself called inside `session_manager.get_lock(user_id)` in `bot.py:851`. So in the single-message path, this is safe. But:

- In `bot.py:911-919`, the gate checks `session.pending_confirmations` **inside** the lock and returns early if non-empty.
- In `bot.py:984-1014` (callback flow), `resolve_confirmations` is called **inside** the lock, and it mutates `session.pending_confirmations` at `agent.py:796,801`.

The mutation happens on different code paths under the same per-user lock, so the lock does serialize them. **However**, `_execute_unanswered_tool_calls` clears the list at line 238 and re-populates it for new tool calls. If a tool call's `_is_out_of_scope` check returns `True` *and* `session.yolo_mode` is `False`, the list is repopulated and `PendingConfirmationError` is raised. That logic is correct — but it depends on `session.yolo_mode` being read **after** the lock is acquired. Confirmed in `bot.py:851-852` and `bot.py:911-912`: both acquire the lock before reading. **OK**, but the implicit contract should be made explicit (a comment, ideally).

**Confidence:** Low (this looks correct on inspection, but the lack of a comment makes future refactors risky).

### P1-4. `_get_int_env` silently coerces invalid integers to the default

**What:** Multiple sites use this pattern: `bot.py:50-60`, `tools/file_ops.py:12-22`, `tools/system_ops.py:28-38` — all identical. The user typo'd `BASH_TIMEOUT_SECONDS=5o` (with an 'o') and the tool silently runs with the default 300s instead of failing fast.

**Where:** three copies of the same function.

**Impact:** Config typos are silently swallowed. Hard to debug. This is duplicated 3× — the duplication is itself a maintainability issue (drift risk).

**Confidence:** High.

**Suggested fix:** Move to `tools/base.py`, log a warning when coercion happens, and consider rejecting negative values explicitly.

## Medium-priority findings (P2 — should fix)

### P2-1. The "is destructive" allowlist can be bypassed by a verb in a tool name (intended, but easy to misuse)

**What:** `_is_destructive_or_sensitive_tool` (`prompt_builder.py:1004-1035`) is a *fail-safe* gate that matches `_DESTRUCTIVE_VERB_TOKENS` against underscore-separated tokens of the tool name. A new tool called `safe_run_kill_orphan` would be flagged as destructive because of the `kill` token, even if it's actually safe. Conversely, `process_termination_helper` *would* be flagged (correctly) because of `termination`. The behavior is correct, but undocumented.

**Suggested fix:** Add a comment in the tool-registration decorator saying "tools whose name contains a destructive verb will trip HITL confirmation; use a non-verb token if you need a bypass."

### P2-2. `error_classifier` matches on substrings of error messages

**What:** `error_classifier.py:25-56` uses `any(x in err_msg for x in ["429", ...])`. A user-supplied prompt that contains the substring `"429"` (or `"rate limit"`, `"blocked"`, etc.) can fool the surrounding logic if a tool echoes the prompt back. In this codebase, the LLM never sees the raw error message, so the risk is low — but the pattern is fragile and would break if a future tool printed the prompt into the error path.

**Suggested fix:** Use structured error codes from the OpenAI/Anthropic SDK instead of substring matching.

### P2-3. `_execute_unanswered_tool_calls` race against `resolve_confirmations`

**What:** At `agent.py:238`, the function clears `session.pending_confirmations`. If `resolve_confirmations` (which is called from the Telegram/Discord callback path under a separate lock acquisition) is mid-execution and an interrupt / cron fires a new `run_agent_turn` simultaneously, the second turn's `_execute_unanswered_tool_calls` will clobber the in-progress list.

In the current code, the cron worker in `bot.py:1303` **does** acquire the same per-user lock — so this is safe today. But the safety is implicit.

**Suggested fix:** Add an assertion that `_execute_unanswered_tool_calls` is only called under `session_manager.get_lock`.

### P2-4. `safe_upload_filename` doesn't normalize Unicode

**What:** `bot.py:194-198` only keeps `isalnum`, `-`, `_`, `.`. Non-Latin filenames (e.g. Cyrillic, Chinese) become empty and fall back to the default. Functional but a UX bug.

### P2-5. `audit_log` writes to a single append-only file with no rotation or flocking

**What:** `tools/base.py:109-123` opens `YOLO_LOG_FILE` in append mode. Multiple async tasks writing concurrently can interleave JSON lines, breaking any future parser. There's also no size cap — a long-running bot will grow this file unboundedly.

**Suggested fix:** Use a single asyncio lock around the file write, or rotate when the file exceeds N MB.

### P2-6. `mcp_manager` initializes but doesn't tear down on bot shutdown

**What:** `bot.py:1446-1451` calls `cancel_all_background_tasks` and `close_db` on shutdown, but never calls `mcp_manager.cleanup()`. The MCP subprocesses linger until the OS reaps them.

**Suggested fix:** Register `mcp_manager.cleanup` in the shutdown path.

### P2-7. `LLMRouter.__init__` swallows exceptions during client creation

**What:** `llm_router.py:149-161` only checks `self.config.provider in {"openai", ...}`. If `OPENAI_BASE_URL` is malformed, the `AsyncOpenAI(...)` constructor will raise — but the constructor is called eagerly, so the failure happens at import time (since `router = _get_router()` runs at module load in `agent.py:66`). A bad env var at startup causes an opaque crash instead of a clean error.

**Suggested fix:** Defer client creation to first call, or wrap in a clear error.

## Low-priority findings (P3 — nice to have)

- **Triple-duplicated `_get_int_env`** (`bot.py:50`, `tools/file_ops.py:12`, `tools/system_ops.py:28`) — should live in `tools/base.py`.
- **Triple-duplicated `escape_markdown`** — only one in `bot.py:106-116`; consider moving to a shared util if a second gateway is added.
- **`llm_router.RateLimiter`** uses `threading.Lock` (line 24) but is called from async code. The lock is only held briefly to update a list, but it could be a regular asyncio lock for clarity. Not a bug.
- **`zip_history_payload`** (`agent.py:375-453`) is well-implemented but has 3x nested `from prompt_builder import log_agent` inside the hot loop (lines 414, 439). Move to module top.
- **`_repo_has_tests`** (`prompt_builder.py:684-736`) is a depth-limited walk that ignores symlinks. If the repo is a symlink farm, it may miss tests.
- **`Session.last_saved_signature`** (`session.py:34`) stores a `hash(...)` result, which is randomized per Python process. The dedup cache is process-local anyway, so this is fine — but the field name is misleading.
- **No test for `_is_out_of_scope`** — the function at `prompt_builder.py:1038` is the only thing stopping a malicious prompt from `read_file("/etc/passwd")` via the `confirm_func` short-circuit. It should have a test.
- **Magic numbers in `bot.py`** (e.g. `4000` chunk size, `3000` notification chunk size, `1900` Discord chunk) are not configurable. Hard to tune without a code change.
- **TUI files** (`tui.py`, `tui_widgets.py`) were not read in depth due to scope; the codebase reviewer's own analysis flagged no obvious defects in passing.

## Architectural observations

- **The "soft-block with confirmation" sandbox model** (`resolve_and_verify_path` + `confirm_func`) is a sound design. It bounds blast radius without hard-failing on legitimate cross-sandbox work. The pattern of "destructive tool name → HITL" combined with "out-of-scope path → HITL" is the right shape.
- **The `pending_confirmations` flow** is a nice human-in-the-loop primitive. The dual-lock-acquisition pattern in `bot.py:851` and `bot.py:911` is correct but would benefit from a `with session.guarded(user_id):` context manager.
- **The MCP integration is well-isolated** — secrets are stripped from subprocess env (line 19, 22-37 of `mcp_manager.py`), and tool-name collisions are namespaced. This is better than most ad-hoc plugin systems.
- **The audit log** is comprehensive but under-consumed — every tool call is logged, but there's no analyzer or rate-limiter on top. Future work: a "suspicious activity" detector.
- **The prompt architecture** is complex but principled. The unified vs. legacy split, the mtime-cached template loader, and the tag-block system are well thought out. The `_normalize_single_system_message` function is the keystone — it would benefit from a property test.
- **Tests are well-targeted** (regression suite in `test_bugfixes.py`) but coverage is concentrated on small, isolated helpers. The full agent loop, the Telegram/Discord gateways, and the `_is_out_of_scope` path are all untested at the integration level.

## What's good

- **Clean module boundaries** — `agent.py` orchestrates, `llm_router.py` routes, `tool_dispatcher.py` dispatches, `session.py` owns state, `prompt_builder.py` builds. No god files (the largest, `bot.py`, is large because it's a command handler table, not because of mixed concerns).
- **Sandboxing is real** — sensitive OS prefixes are hard-blocked, and out-of-scope paths require confirmation. The path traversal in `resolve_and_verify_path` correctly uses `Path.resolve()` and `relative_to` rather than string matching.
- **MCP subprocess isolation** is the right call — secrets are stripped, namespaces prevent collisions, and timeouts prevent zombie servers.
- **Rate limiting on the LLM** (`llm_router.py:19-55`) with a sleep-outside-lock pattern is correct and avoids blocking the event loop.
- **The thinking-mode auto-detection** (`prompt_builder.py:375-393`) with negation-aware whole-word matching is a thoughtful touch — "no, don't refactor" correctly fails to trigger refactor mode.
- **Session save signature dedup** (`session.py:91-148`) is a real performance optimization that prevents redundant SQLite writes on hot paths.
- **The audit trail is comprehensive** — every tool call, retry, error, and notification is logged with structured JSON. This makes postmortem work tractable.
- **Test discipline** — `test_bugfixes.py` pins specific fixes so they can't silently regress. This is the right pattern.

## Skipped / out of scope

- `tui.py`, `tui_widgets.py`, `tui.tcss` — Textual UI rendering; not security-critical and not read in depth.
- `tools/gui_ops.py` (40KB) — desktop automation via `pyautogui`/`cv2`; only cursor-click-based invocation, gated by the destructive-tool check. Should be reviewed separately.
- `tools/browser_ops.py` (22KB) — browser automation; read in passing.
- `tools/team_ops.py` (15KB) — multi-agent orchestration; not read in depth.
- `tools/web_ops.py`, `tools/research_ops.py`, `tools/skill_ops.py`, `tools/cron_ops.py`, `tools/memory_ops.py`, `tools/mission_ops.py`, `tools/identity_ops.py`, `tools/artifact_ops.py`, `tools/document_parser.py`, `tools/codebase_ops.py`, `tools/git_ops.py`, `tools/media_ops.py`, `tools/evolution_ops.py`, `tools/experience_ops.py`, `tools/memory_service.py`, `tools/yolo_memory.py`, `tools/plugin_manager.py`, `tools/background_ops.py`, `tools/database_ops.py`, `tools/settings.py`, `tools/registry.py` — only skimmed.
- `worker.py`, `whisper_local.py`, `monitoring.py`, `health_server.py`, `server.py` — read in passing; no defects found at the surface.
- The 12 `verify_phase*.py` scripts and `verify_widgets.py` — not read.
- The `.claude/`, `desktop/`, `playground/`, `artifacts/`, `docs/`, `skills/`, `tests/chaos/` directories — out of scope.
- **No tests were run** — this review is static-only.

---

**Reviewer agent file:** [codebase-reviewer.md](file:///home/dharshan/.claude/agents/codebase-reviewer.md) — usable for future reviews by passing a target directory.

**Summary for triage:** The codebase is well-engineered overall. The two real P0s are the Discord allow-list inversion and the broken `memory_service` propagation in the HITL flow. Everything else is incremental hardening. The biggest gap is **test coverage on the safety-critical paths** — the destructive-tool gate, the `_is_out_of_scope` check, and the gateway authentication are all production-load-bearing but lightly tested.
