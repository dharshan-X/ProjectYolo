# Yolo as Model for Claude Code / Codex / Cursor

Yolo can act as an **OpenAI-compatible and Responses-compatible model server** so external agentic CLIs use Yolo's full brain (60+ tools, memory, workers) instead of calling Anthropic/OpenAI directly.

The server exposes Yolo's `run_agent_turn` (`agent.py:830`) behind:
- `POST /v1/responses` (OpenAI Responses API with streaming tool calls, used by Codex)
- `POST /v1/chat/completions` (OpenAI Chat Completions API)
- `POST /v1/messages` (Anthropic Messages API)
- `GET /v1/models` (Codex capability handshake and model catalog)

## Architecture

```
Codex (wire_api = "responses") ─────┐
Claude Code (ANTHROPIC_BASE_URL) ───┼──► yolo_model_server.py :8788
Cursor / OpenAI-compat ─────────────┘         POST /v1/responses (Responses API)
                                              POST /v1/chat/completions (OpenAI)
                                              POST /v1/messages (Anthropic)
                                              GET  /v1/models
                                              SSE streams: event: ...  data: {...}
                                              │
                                              └──► SessionManager session.py:45
                                                   → agent.run_agent_turn agent.py:830
```

**Execution Modes:**
- **Hybrid Tool Execution (Codex):** Client tools declared by Codex (`exec_command`, `apply_patch`) are yielded back to Codex via OpenAI Responses API `function_call` streaming events for sandboxed local execution. YOLO internal tools (tiered memory, background swarm workers, web research, GUI perception) execute natively inside the YOLO cognitive turn.
- **Opaque Agent (Default for chat/completions):** YOLO executes its own tools (`yolo_mode=True` `session.py:21`) internally and returns final text. Incoming `tools` from caller are ignored unless `YOLO_MODEL_TOOL_PASSTHROUGH=true`.

## Quick Start

### 1. Start server

```bash
# Standalone
python yolo_model_server.py
# or via server.py (also starts health :8787)
python server.py --mode yolo-model
# or all gateways + model
python server.py --mode all
# Env overrides:
YOLO_MODEL_HOST=127.0.0.1 YOLO_MODEL_PORT=8788 python yolo_model_server.py
```

Server logs:
```
[yolo-model] Listening on http://127.0.0.1:8788
[yolo-model] Responses API: http://127.0.0.1:8788/v1/responses
[yolo-model] OpenAI compat: http://127.0.0.1:8788/v1/chat/completions
[yolo-model] Anthropic compat: http://127.0.0.1:8788/v1/messages
[yolo-model] Models: http://127.0.0.1:8788/v1/models
```

### 2. Configure clients

**Codex** `~/.codex/config.toml`:
```toml
model_provider = "yolo"
model = "yolo" # or "gpt-5.6-terra"

[model_providers.yolo]
name = "Yolo"
base_url = "http://127.0.0.1:8788/v1"
wire_api = "responses"
api_key = "yolo-local"
```

**Claude Code** (Anthropic compat):
```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8788/v1"
export ANTHROPIC_API_KEY="yolo-local"
claude -p "use read_file to summarize README"
```

**OpenAI-compat fallback** (Cursor/Opencode):
```bash
export OPENAI_BASE_URL="http://127.0.0.1:8788/v1"
export OPENAI_API_KEY="yolo-local"
```

### 3. Verify

```bash
# Health (no auth)
curl http://127.0.0.1:8788/health | jq
curl http://127.0.0.1:8788/v1/models -H "Authorization: Bearer yolo-local" | jq

# Non-stream
curl -s http://127.0.0.1:8788/v1/chat/completions \
  -H "Authorization: Bearer yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"yolo","messages":[{"role":"user","content":"list files via list_dir"}]}' | jq

# Stream
curl -N http://127.0.0.1:8788/v1/chat/completions \
  -H "Authorization: Bearer yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"yolo","messages":[{"role":"user","content":"hello"}],"stream":true}'

# Anthropic non-stream
curl -s http://127.0.0.1:8788/v1/messages \
  -H "x-api-key: yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"yolo","messages":[{"role":"user","content":"hello"}]}' | jq

# Anthropic stream
curl -N http://127.0.0.1:8788/v1/messages \
  -H "x-api-key: yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"yolo","messages":[{"role":"user","content":"hello"}],"stream":true}'

# Responses API (Codex format - stream)
curl -N http://127.0.0.1:8788/v1/responses \
  -H "Authorization: Bearer yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.6-terra","stream":true,"input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"Run tests"}]}],"tools":[{"type":"function","name":"exec_command","parameters":{}}]}'

# Responses API (Non-stream)
curl -s http://127.0.0.1:8788/v1/responses \
  -H "Authorization: Bearer yolo-local" -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.6-terra","input":"Hello"}' | jq
```

## Codex Integration & Hybrid Tool Execution

Codex communicates with YOLO using the OpenAI **Responses API** (`wire_api = "responses"`).

### Hybrid Tool Execution Architecture

In this hybrid architecture:
- **Client Tools (`exec_command`, `apply_patch`)**: Yielded back to Codex via OpenAI Responses API streaming `function_call` events (`response.output_item.added`, `response.function_call_arguments.delta/done`, `response.completed`). Codex executes the tool in its local sandbox and provides the result back in Turn 2 using a `function_call_output` item in `input`.
- **YOLO Internal Tools**: Tools native to YOLO (Tiered Memory `yolo_memory`, swarm worker orchestration `spawn_worker`, stealth web browser research `camoufox`, and Wayland/X11 GUI perception) execute inside YOLO's Think-Act-Observe cognitive loop without leaving YOLO.

### Responses API Endpoints

1. **`GET /v1/models?client_version=...`**:
   - Codex client capability handshake.
   - Returns models with:
     - `truncation_policy`: `{"mode": "auto"}`
     - `supported_reasoning_levels`: includes `ultra` (Ultra Deep Thinking)
     - Capability flags: `shell_type: "unified_exec"`, `apply_patch_tool_type: "freeform"`, `web_search_tool_type: "text_and_image"`
     - Models: `gpt-5.6-terra` (default Codex alias), `yolo`, `yolo-think`, `yolo-safe`

2. **`POST /v1/responses`**:
   - Handles multi-turn streaming via Server-Sent Events (SSE).
   - **Turn 1 (Prompt + Tools -> Client Tool Dispatch):**
     - Codex sends `input` messages and client `tools`.
     - When YOLO calls a client tool, it emits `YOLO_CLIENT_TOOL:` signal.
     - SSE stream produces: `response.created`, `response.in_progress`, `response.output_item.added` (`type: "function_call"`), `response.function_call_arguments.delta` / `done`, `response.output_item.done`, `response.completed`.
   - **Turn 2 (Tool Output -> Text Completion):**
     - Codex executes the tool and sends `input` containing the `function_call_output` item.
     - YOLO normalizes the input, executes the next cognitive step with the tool output, and streams text deltas: `response.output_text.delta`, `response.output_text.done`, `response.content_part.done`, `response.output_item.done`, `response.completed`.

### 4. Models

- `yolo` — default, `yolo_mode=True` `session.py:21`, `think_mode` auto (`prompt_builder.py:453`)
- `yolo-think` — `think_mode=force_on` `session.py:22`, forces `<thought>` planning `prompt_builder.py:342`
- `yolo-safe` — `yolo_mode=False`, destructive tools require HITL `prompt_builder.py:1227` (will return `[Blocked: ...]` if caller didn't confirm)
- `gpt-5.6-terra` — alias for Codex compatibility with ultra-deep reasoning level

All also list Yolo's underlying LLM (`router.config.model` `llm_router.py:246`).

### 5. Env

```env
YOLO_MODEL_HOST=127.0.0.1
YOLO_MODEL_PORT=8788
YOLO_MODEL_API_KEYS=yolo-local,sk-...   # comma-separated Bearer tokens
YOLO_MODEL_DISABLE_AUTH=false            # true disables auth (dev)
YOLO_MODEL_TOOL_PASSTHROUGH=false
```

See `.env.example` for defaults.

### 6. Security

- Auth via `Authorization: Bearer <key>` (`yolo_model_server.py:47` `hmac.compare_digest`) or `x-api-key` (Anthropic).
- Per-key `user_id` isolation `hash(api_key)` → `Session(user_id)` `session.py:16`.
- Env stripping for MCP-like future passthrough reuses `_MCP_SECRET_MARKERS` `tools/mcp_manager.py:36`.
- Audit via `tools/base.py:126` `audit_log`.

### 7. Troubleshooting

- `401 Invalid API key` → check `YOLO_MODEL_API_KEYS` includes your `Bearer` value or set `YOLO_MODEL_DISABLE_AUTH=true` for local.
- `Port 8788 in use` → `YOLO_MODEL_PORT=8789`
- Empty response → ensure underlying LLM configured (`LLM_PROVIDER`, `OPENAI_API_KEY` etc. `llm_router.py:187`); check `health` `model` field.
- `No gateway selected` → `server.py --mode yolo-model` (not `telegram`).

### 8. Tests

```bash
# E2E Codex handshake & multi-turn verification
.venv/bin/pytest tests/test_codex_e2e_integration.py -v

# Model server unit & integration tests
.venv/bin/pytest tests/test_yolo_model_server.py -v
```
