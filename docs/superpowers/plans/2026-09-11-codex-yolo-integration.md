# Codex & YOLO Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully connect Project YOLO to Codex CLI and Desktop as its primary model provider with hybrid tool execution, enabling Codex to execute sandbox commands and patches while YOLO drives intelligence and reasoning.

**Architecture:** Update `yolo_model_server.py` to support Codex 0.154.0+ model schemas (`truncation_policy`, `ultra` reasoning), ingest Codex client tools from `POST /v1/responses`, stream Responses API `function_call` SSE events, and normalize `function_call_output` turns into conversational history.

**Tech Stack:** Python 3.9+, Asyncio, Aiohttp, Pytest (`.venv/bin/pytest`).

## Global Constraints

- **Python Virtual Environment**: Always use `.venv/bin/pytest` for testing.
- **Port & Endpoints**: Maintain Responses API on `POST /v1/responses` and Model metadata on `GET /v1/models`.
- **Protocol Fidelity**: Comply strictly with OpenAI Responses API SSE event specifications (`response.output_item.added`, `response.function_call_arguments.delta`, `response.completed`).
- **Audit Logging**: Maintain `audit_log` invocations on tool registration and execution paths.

---

### Task 1: Codex Model Handshake Compatibility (`GET /v1/models`)

**Files:**
- Modify: `yolo_model_server.py:283-335`
- Test: `tests/test_yolo_model_server.py`

**Interfaces:**
- Produces: `_model_entry(mid, disp)` returning dictionary containing `truncation_policy: {"mode": "auto"}` and `supported_reasoning_levels` including `ultra`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_yolo_model_server.py`:
```python
@pytest.mark.anyio
async def test_models_schema_codex_compat():
    yolo_model_server, app = _make_app(disable_auth=True)
    from aiohttp.test_utils import TestClient, TestServer
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/v1/models")
        assert resp.status == 200
        data = await resp.json()
        models = data.get("data", [])
        assert len(models) > 0
        for m in models:
            assert "truncation_policy" in m
            assert m["truncation_policy"] == {"mode": "auto"}
            effort_levels = [lvl["effort"] for lvl in m.get("supported_reasoning_levels", [])]
            assert "ultra" in effort_levels
        # Ensure default Codex model gpt-5.6-terra is present or aliased
        model_ids = {m["id"] for m in models}
        assert "gpt-5.6-terra" in model_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_models_schema_codex_compat -v`
Expected: FAIL (missing `truncation_policy`, missing `ultra`, or missing `gpt-5.6-terra`).

- [ ] **Step 3: Implement model schema updates**

In `yolo_model_server.py`, update `_model_entry()`:
```python
def _model_entry(mid: str, disp: str):
    return {
        "id": mid,
        "object": "model",
        "created": now,
        "owned_by": "yolo",
        "slug": mid,
        "display_name": disp,
        "description": f"Yolo agent model {mid}",
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low", "description": "Fast"},
            {"effort": "medium", "description": "Balanced"},
            {"effort": "high", "description": "Deep"},
            {"effort": "ultra", "description": "Ultra Deep Thinking"},
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
And in `handle_list_models()`, add `"gpt-5.6-terra"` to `models`:
```python
models = [
    _model_entry("yolo", "Yolo"),
    _model_entry("yolo-think", "Yolo Think"),
    _model_entry("yolo-safe", "Yolo Safe"),
    _model_entry("gpt-5.6-terra", "Yolo Terra (Codex)"),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_models_schema_codex_compat -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yolo_model_server.py tests/test_yolo_model_server.py
git commit -m "feat(model-server): add Codex 0.154+ schema compatibility to /v1/models"
```

---

### Task 2: Ingestion of Codex Tools and `function_call_output`

**Files:**
- Modify: `yolo_model_server.py:220-275, 750-775`
- Test: `tests/test_yolo_model_server.py`

**Interfaces:**
- Consumes: `raw_input` list from `POST /v1/responses`.
- Produces: `_extract_responses_input(data)` supporting items where `type == "function_call_output"`, mapping to `{"role": "tool", "tool_call_id": call_id, "content": output}`. Attaches `client_tools` to `Session`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_yolo_model_server.py`:
```python
def test_extract_responses_input_function_call_output():
    yolo_model_server, _ = _make_app(disable_auth=True)
    raw_data = {
        "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]},
            {
                "type": "function_call_output",
                "call_id": "call_pytest_001",
                "output": "12 passed in 0.45s",
            },
        ],
        "tools": [
            {
                "type": "function",
                "name": "exec_command",
                "description": "Execute a command in Codex sandbox",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
            }
        ],
    }
    messages = yolo_model_server._extract_responses_input(raw_data)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Run tests"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call_pytest_001"
    assert messages[1]["content"] == "12 passed in 0.45s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_extract_responses_input_function_call_output -v`
Expected: FAIL (does not recognize `function_call_output`).

- [ ] **Step 3: Implement `function_call_output` handling & tool extraction**

In `yolo_model_server.py`, update `_extract_responses_input()`:
```python
def _extract_responses_input(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_input = data.get("input") or []
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if not isinstance(raw_input, list):
        return []

    messages: List[Dict[str, Any]] = []
    for item in raw_input:
        if not isinstance(item, dict):
            messages.append({"role": "user", "content": str(item)})
            continue

        item_type = item.get("type", "")
        if item_type == "function_call_output":
            call_id = item.get("call_id") or item.get("id") or ""
            out = item.get("output", "")
            if isinstance(out, (dict, list)):
                out = json.dumps(out)
            messages.append({"role": "tool", "tool_call_id": str(call_id), "content": str(out)})
            continue

        role = item.get("role", "user")
        content = item.get("content", "")
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict):
                    t = p.get("text") or p.get("input_text") or ""
                    if t:
                        parts.append(str(t))
            content = " ".join(parts).strip()
        messages.append({"role": role, "content": str(content) if content is not None else ""})

    return messages
```
And in `_build_yolo_session()` or `handle_responses()`, attach `client_tools`:
```python
client_tools = data.get("tools", [])
if hasattr(session, "__dict__"):
    session.client_tools = client_tools
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_extract_responses_input_function_call_output -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yolo_model_server.py tests/test_yolo_model_server.py
git commit -m "feat(model-server): support function_call_output ingestion and client_tools attachment"
```

---

### Task 3: Streaming Function Call Emission in Responses SSE

**Files:**
- Modify: `yolo_model_server.py:831-925` (`_handle_responses_stream`)
- Test: `tests/test_yolo_model_server.py`

**Interfaces:**
- Produces: Responses API streaming events when a client tool is called (`response.output_item.added`, `response.function_call_arguments.delta/done`, `response.completed`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_yolo_model_server.py`:
```python
@pytest.mark.anyio
async def test_responses_streaming_emits_function_call(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=True)
    from aiohttp.test_utils import TestClient, TestServer

    # Mock run_agent_turn to emit a client tool call
    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        if signal_handler:
            # Emit tool call signal
            call_payload = json.dumps({
                "call_id": "call_cmd_42",
                "name": "exec_command",
                "arguments": {"command": "pytest tests/"},
            })
            await signal_handler(f"YOLO_CLIENT_TOOL:{call_payload}")
        return "[Tool dispatched to client]"

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        req_payload = {
            "model": "yolo",
            "stream": True,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]}],
            "tools": [{"type": "function", "name": "exec_command", "parameters": {}}],
        }
        resp = await client.post("/v1/responses", json=req_payload)
        assert resp.status == 200
        text = await resp.text()
        assert "response.output_item.added" in text
        assert "function_call" in text
        assert "call_cmd_42" in text
        assert "exec_command" in text
        assert "response.function_call_arguments.done" in text
        assert "response.completed" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_responses_streaming_emits_function_call -v`
Expected: FAIL (does not emit `function_call` event in SSE stream).

- [ ] **Step 3: Implement streaming function call serializer**

In `yolo_model_server.py`, update `_handle_responses_stream()`:
Handle `signal_text` starting with `YOLO_CLIENT_TOOL:` in `_signal_handler`:
```python
if signal_text.startswith("YOLO_CLIENT_TOOL:"):
    tool_info = json.loads(signal_text[len("YOLO_CLIENT_TOOL:"):])
    await stream_queue.put(("function_call", tool_info))
```
In event processing loop of `_handle_responses_stream`:
```python
if event_type == "function_call":
    call_id = payload.get("call_id", f"call_{uuid.uuid4().hex[:8]}")
    name = payload.get("name", "exec_command")
    args = payload.get("arguments", {})
    args_str = json.dumps(args) if isinstance(args, dict) else str(args)

    item = {
        "id": call_id,
        "type": "function_call",
        "name": name,
        "call_id": call_id,
        "status": "in_progress",
        "arguments": "",
    }
    await resp.write(f"event: response.output_item.added\ndata: {json.dumps({'type':'response.output_item.added','output_index':0,'item':item})}\n\n".encode())
    await resp.write(f"event: response.function_call_arguments.delta\ndata: {json.dumps({'type':'response.function_call_arguments.delta','output_index':0,'item_id':call_id,'call_id':call_id,'delta':args_str})}\n\n".encode())
    await resp.write(f"event: response.function_call_arguments.done\ndata: {json.dumps({'type':'response.function_call_arguments.done','output_index':0,'item_id':call_id,'call_id':call_id,'arguments':args_str})}\n\n".encode())
    item["status"] = "completed"
    item["arguments"] = args_str
    await resp.write(f"event: response.output_item.done\ndata: {json.dumps({'type':'response.output_item.done','output_index':0,'item':item})}\n\n".encode())

    # Complete response for this tool dispatch turn
    completed = {
        "type": "response.completed",
        "response": {
            "id": resp_id,
            "object": "response",
            "status": "completed",
            "model": model,
            "output": [item],
        },
    }
    await resp.write(f"event: response.completed\ndata: {json.dumps(completed)}\n\n".encode())
    break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_responses_streaming_emits_function_call -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yolo_model_server.py tests/test_yolo_model_server.py
git commit -m "feat(model-server): implement Responses API function_call event streaming"
```

---

### Task 4: Dynamic Tool Routing Between YOLO and Client Tools

**Files:**
- Modify: `yolo_model_server.py`, `agent.py`
- Test: `tests/test_yolo_model_server.py`

**Interfaces:**
- Consumes: `session.client_tools` list.
- Produces: Signal `YOLO_CLIENT_TOOL:` when LLM selects a client tool (`exec_command`, `apply_patch`), delegating execution to the client stream.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_yolo_model_server.py`:
```python
@pytest.mark.anyio
async def test_client_tool_routing_signal(monkeypatch):
    from session import Session
    session = Session(user_id=123)
    session.client_tools = [
        {"type": "function", "name": "exec_command", "parameters": {}}
    ]

    emitted_signals = []
    async def capture_signal(sig):
        emitted_signals.append(sig)

    yolo_model_server, _ = _make_app(disable_auth=True)
    routed = yolo_model_server._route_or_execute_tool(
        tool_name="exec_command",
        arguments={"command": "ls -la"},
        session=session,
        signal_handler=capture_signal
    )
    assert asyncio.iscoroutine(routed)
    res = await routed
    assert res == "__CLIENT_TOOL_DISPATCHED__"
    assert any("YOLO_CLIENT_TOOL:" in s for s in emitted_signals)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_client_tool_routing_signal -v`
Expected: FAIL (`_route_or_execute_tool` not defined).

- [ ] **Step 3: Implement client tool router**

In `yolo_model_server.py`, implement `_route_or_execute_tool`:
```python
async def _route_or_execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    session: Any,
    signal_handler: Optional[Callable[[str], Awaitable[None]]] = None,
) -> str:
    client_tools = getattr(session, "client_tools", [])
    client_tool_names = {
        t.get("name") or t.get("function", {}).get("name")
        for t in client_tools
        if isinstance(t, dict)
    }

    if tool_name in client_tool_names:
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        if signal_handler:
            payload = json.dumps({"call_id": call_id, "name": tool_name, "arguments": arguments})
            await signal_handler(f"YOLO_CLIENT_TOOL:{payload}")
        return "__CLIENT_TOOL_DISPATCHED__"

    # Otherwise fallback to YOLO native execution
    from tool_dispatcher import execute_tool_direct
    return await execute_tool_direct(tool_name, arguments, user_id=getattr(session, "user_id", 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_yolo_model_server.py::test_client_tool_routing_signal -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yolo_model_server.py tests/test_yolo_model_server.py
git commit -m "feat(model-server): add client tool routing helper"
```

---

### Task 5: End-to-End Handshake & Multi-Turn Verification

**Files:**
- Create: `tests/test_codex_e2e_integration.py`
- Modify: `docs/yolo-as-model.md`

**Interfaces:**
- Validates the complete cycle:
  1. `GET /v1/models` verifies `truncation_policy` and `gpt-5.6-terra`.
  2. `POST /v1/responses` initiates turn with tools and yields `exec_command`.
  3. Subsequent `POST /v1/responses` with `function_call_output` finishes with text output.

- [ ] **Step 1: Write the end-to-end integration test**

Create `tests/test_codex_e2e_integration.py`:
```python
import pytest
from aiohttp.test_utils import TestClient, TestServer
import yolo_model_server

@pytest.mark.anyio
async def test_codex_full_handshake_and_tool_turn():
    app = yolo_model_server.create_app()
    async with TestClient(TestServer(app)) as client:
        # 1. Codex Model Discovery
        resp = await client.get("/v1/models?client_version=0.154.0")
        assert resp.status == 200
        data = await resp.json()
        models = {m["id"]: m for m in data.get("data", [])}
        assert "gpt-5.6-terra" in models
        assert models["gpt-5.6-terra"]["truncation_policy"] == {"mode": "auto"}

        # 2. Turn 1: Codex sends prompt with exec_command tool
        payload_1 = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]}],
            "tools": [{"type": "function", "name": "exec_command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}],
        }
        resp_1 = await client.post("/v1/responses", json=payload_1)
        assert resp_1.status == 200
        body_1 = await resp_1.text()
        assert "response.completed" in body_1

        # 3. Turn 2: Codex returns tool output
        payload_2 = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]},
                {"type": "function_call_output", "call_id": "call_123", "output": "All 12 tests passed!"},
            ],
            "tools": [{"type": "function", "name": "exec_command", "parameters": {}}],
        }
        resp_2 = await client.post("/v1/responses", json=payload_2)
        assert resp_2.status == 200
        body_2 = await resp_2.text()
        assert "response.completed" in body_2
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_codex_e2e_integration.py -v`
Expected: PASS

- [ ] **Step 3: Update documentation**

In `docs/yolo-as-model.md`, update the Codex section to document the Hybrid Tool Passthrough mode.

- [ ] **Step 4: Commit**

```bash
git add tests/test_codex_e2e_integration.py docs/yolo-as-model.md
git commit -m "test: add comprehensive end-to-end integration test for Codex and YOLO"
```
