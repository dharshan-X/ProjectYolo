# Design Specification: Codex & YOLO Integration (Hybrid Execution & Responses Protocol Bridge)

**Date**: 2026-09-11  
**Status**: Approved  
**Topic**: Codex Model Provider Integration with Tool Passthrough and Hybrid Execution  

---

## 1. Executive Summary & Goals

This specification defines the architectural design to fully connect **Project YOLO** with the **Codex CLI / Desktop** ecosystem. 

YOLO serves as the primary model and cognitive intelligence provider for Codex (running locally at `http://127.0.0.1:8788/v1` via Codex's `wire_api = "responses"`), while Codex operates as the execution harness. 

Instead of running as a black-box opaque text generator, YOLO operates in a **Hybrid Execution** model:
1. **Codex Client Tools**: Coding actions that mutate or inspect the local workspace (such as `exec_command` in Codex's sandbox and `apply_patch`) are delegated to Codex via standard Responses API `function_call` streaming events.
2. **YOLO Internal Tools**: Deep reasoning capabilities (4-tier persistent memory, Swarm Lead delegations, and stealth research) remain in-process within YOLO, augmenting the context before or during tool invocation.
3. **Protocol Handshake Compatibility**: Resolves Codex 0.154.0+ model decoding requirements (`truncation_policy`, ultra reasoning effort, and shell configuration) so Codex connects reliably without errors.

---

## 2. Architectural Map

```
Codex CLI / Desktop (Client)
  │
  ├── 1. Handshake: GET /v1/models?client_version=0.154.0
  │      └── Returns model metadata with truncation_policy & ultra reasoning
  │
  ├── 2. Turn Request: POST /v1/responses
  │      ├── Input: Conversation turns, client_id, thread_id
  │      └── Tools: Codex sandbox tools [exec_command, apply_patch, web_search, plugins]
  │
  ▼
yolo_model_server.py :8788 (Responses API Bridge)
  │
  ├── Session Management: Isolate thread_id / client_id in session.py
  ├── Dynamic Tool Registration: Register Codex client tools into active turn
  │
  ▼
Agent Core (agent.py) & LLM Router (llm_router.py)
  ├── Step A: Internal Tool Execution (L1-L4 Tiered Memory, Swarm workers)
  └── Step B: Client Tool Decision (exec_command, apply_patch)
  │
  ▼
Streaming Event Serializer (_handle_responses_stream)
  │
  ├── SSE: response.output_item.added (type: "function_call", name, call_id)
  ├── SSE: response.function_call_arguments.delta (chunked JSON args)
  ├── SSE: response.function_call_arguments.done
  └── SSE: response.completed
  │
  ▼
Codex Local Sandbox Execution
  │
  └── Returns POST /v1/responses (input: [function_call_output: {call_id, output}])
```

---

## 3. Detailed Specifications

### 3.1 Codex Model Handshake (`GET /v1/models`)

Codex 0.154.0+ enforces strict validation of model properties. The server endpoint must supply these fields in `_model_entry()`:

```python
{
    "id": model_id,
    "object": "model",
    "created": now,
    "owned_by": "yolo",
    "slug": model_id,
    "display_name": display_name,
    "description": f"Yolo agent model {model_id}",
    "default_reasoning_level": "medium",
    "supported_reasoning_levels": [
        {"effort": "low", "description": "Fast"},
        {"effort": "medium", "description": "Balanced"},
        {"effort": "high", "description": "Deep"},
        {"effort": "ultra", "description": "Ultra Deep Thinking"}
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
    "context_window": 272000,
    "max_context_window": 872000,
}
```

Aliases must ensure `gpt-5.6-terra` (Codex default model) maps directly to the active YOLO model configuration.

### 3.2 Tool Discovery & Dynamic Registration

When Codex calls `POST /v1/responses`, the request body includes:
- `tools`: An array of tool schemas provided by Codex (`exec_command`, `apply_patch`, etc.).
- `input`: An array of input items containing text messages or `function_call_output` records.

#### Processing Steps:
1. Extract `tools` from the JSON payload.
2. In `_build_yolo_session()`, store the client tool schemas on the `Session` instance (`session.client_tools = tools`).
3. During LLM prompt construction in `prompt_builder.py` or when preparing tool definitions for `llm_router.py`, combine:
   - YOLO's internal reasoning tools (`yolo_memory`, `team_ops`).
   - Codex's client execution tools (`exec_command`, `apply_patch`).

### 3.3 Responses Protocol Event Serialization

When YOLO's LLM emits a tool call for a client-side tool (e.g. `exec_command`):
1. **Output Item Added**:
   ```
   event: response.output_item.added
   data: {"type": "response.output_item.added", "output_index": 0, "item": {"id": "call_abc123", "type": "function_call", "name": "exec_command", "call_id": "call_abc123", "status": "in_progress", "arguments": ""}}
   ```
2. **Argument Streaming**:
   ```
   event: response.function_call_arguments.delta
   data: {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "call_abc123", "call_id": "call_abc123", "delta": "{\"command\": \"pytest tests/\"}"}
   ```
3. **Argument Done**:
   ```
   event: response.function_call_arguments.done
   data: {"type": "response.function_call_arguments.done", "output_index": 0, "item_id": "call_abc123", "call_id": "call_abc123", "arguments": "{\"command\": \"pytest tests/\"}"}
   ```
4. **Output Item Completed**:
   ```
   event: response.output_item.done
   data: {"type": "response.output_item.done", "output_index": 0, "item": {"id": "call_abc123", "type": "function_call", "name": "exec_command", "call_id": "call_abc123", "status": "completed", "arguments": "{\"command\": \"pytest tests/\"}"}}
   ```
5. **Turn Completed**:
   ```
   event: response.completed
   data: {"type": "response.completed", "response": {"id": "resp_123", "status": "completed", "output": [...]}}
   ```

### 3.4 Receiving Tool Outputs (`function_call_output`)

When Codex finishes executing the command in its sandbox, it sends the next turn to `POST /v1/responses`:
```json
{
  "type": "function_call_output",
  "call_id": "call_abc123",
  "output": "12 passed in 1.45s"
}
```
YOLO's parser in `_extract_responses_input()` will identify `function_call_output` items and normalize them into OpenAI tool message format:
```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "12 passed in 1.45s"
}
```
This updates the session history, allowing YOLO to observe the tool results and determine the next step.

---

## 4. Error Handling & Edge Cases

1. **Client Tool Rejections & Sandbox Denials**:
   When Codex denies a command or fails with non-zero exit codes, the error string is delivered in `function_call_output`. YOLO's cognitive loop inspects the failure and generates self-correction steps.
2. **Keep-Alive Heartbeats**:
   If YOLO is running internal memory synthesis or swarm orchestration that takes longer than 5 seconds without emitting streaming text, the server writes `: keepalive\n\n` comments every 5 seconds.
3. **Session Reconnection**:
   Codex sessions pass `thread_id` and `client_id`. Sessions persist across HTTP turn requests in `yolo_model_server.py` using per-thread locks.
4. **Client Cancellation**:
   Catches `asyncio.CancelledError` on client disconnects to prevent hung background tasks.

---

## 5. Verification & Testing

1. **Unit Test Suite (`tests/test_yolo_model_server.py`)**:
   - Test `truncation_policy` presence in `GET /v1/models`.
   - Test `ultra` reasoning effort in model list.
   - Test tool definition parsing from `POST /v1/responses`.
   - Test streaming `function_call` event emission.
   - Test `function_call_output` parsing and session history mapping.
2. **Integration Verification**:
   - Run `python yolo_model_server.py`.
   - Run `codex exec "say hello"` and verify end-to-end handshake.
   - Run `codex exec "run pytest tests/test_yolo_model_server.py"` and verify sandboxed execution of `exec_command` through YOLO.
