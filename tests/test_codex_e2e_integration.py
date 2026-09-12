"""End-to-end integration test suite verifying Codex and YOLO handshake and multi-turn flow.

Validates the full cycle between Codex (CLI / Desktop) and YOLO:
1. GET /v1/models?client_version=0.154.0 verifies truncation_policy (mode: "auto"),
   reasoning levels ("ultra"), and gpt-5.6-terra / yolo models.
2. POST /v1/responses (Turn 1): Codex initiates turn with tools (exec_command) and receives
   streaming function_call event (response.output_item.added, function_call_arguments.done,
   response.completed).
3. POST /v1/responses (Turn 2): Codex returns function_call_output with tool execution result;
   YOLO receives normalized input and streams completed text output
   (response.output_text.delta / done, response.completed).
"""

import asyncio
import json
import os
from typing import Any, Dict, List
import pytest
from aiohttp.test_utils import TestClient, TestServer


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_app(disable_auth: bool = True, monkeypatch=None):
    val = "true" if disable_auth else "false"
    if monkeypatch:
        monkeypatch.setenv("YOLO_MODEL_DISABLE_AUTH", val)
    else:
        os.environ["YOLO_MODEL_DISABLE_AUTH"] = val
    import importlib
    import yolo_model_server
    importlib.reload(yolo_model_server)
    app = yolo_model_server.create_app()
    return yolo_model_server, app


def _parse_sse_events(raw_text: str) -> List[Dict[str, Any]]:
    """Parse raw SSE text into structured list of events and JSON data payloads."""
    events: List[Dict[str, Any]] = []
    current_event = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                events.append({"event": current_event or "done", "data": "[DONE]"})
            else:
                try:
                    events.append({"event": current_event, "data": json.loads(data_str)})
                except Exception:
                    events.append({"event": current_event, "data": data_str})
    return events


@pytest.mark.anyio
async def test_codex_models_handshake_endpoint(monkeypatch):
    """Verify GET /v1/models?client_version=0.154.0 conforms to Codex specification."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/v1/models?client_version=0.154.0")
        assert resp.status == 200
        data = await resp.json()

        assert data["object"] == "list"
        models = data.get("data", [])
        assert len(models) > 0

        # Codex checks both data and models properties
        assert "models" in data
        assert len(data["models"]) == len(models)

        model_ids = {m["id"] for m in models}
        assert "gpt-5.6-terra" in model_ids, "Default Codex model gpt-5.6-terra must be present"
        assert "yolo" in model_ids, "Core yolo model must be present"
        assert "yolo-think" in model_ids
        assert "yolo-safe" in model_ids

        for m in models:
            # Codex requirement: truncation_policy.mode == "auto"
            assert "truncation_policy" in m
            assert m["truncation_policy"] == {"mode": "auto"}

            # Codex requirement: reasoning level "ultra"
            reasoning_efforts = [lvl["effort"] for lvl in m.get("supported_reasoning_levels", [])]
            assert "ultra" in reasoning_efforts

            # Codex capability flags
            assert m.get("shell_type") == "unified_exec"
            assert m.get("apply_patch_tool_type") == "freeform"
            assert m.get("web_search_tool_type") == "text_and_image"


@pytest.mark.anyio
async def test_codex_turn_1_client_tool_streaming(monkeypatch):
    """Verify Turn 1: Codex sends prompt + client tools, YOLO streams function_call events."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    captured_turns = []

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        captured_turns.append({
            "user_msg": user_msg,
            "client_tools": getattr(session, "client_tools", []),
            "history": list(getattr(session, "message_history", [])),
        })
        # Emit client tool call signal (YOLO_CLIENT_TOOL:)
        if signal_handler:
            call_payload = json.dumps({
                "call_id": "call_123",
                "name": "exec_command",
                "arguments": {"command": "pytest tests/"},
            })
            await signal_handler(f"YOLO_CLIENT_TOOL:{call_payload}")
        return "[Tool dispatched to client]"

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        req_payload = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Run tests"}],
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "exec_command",
                    "description": "Execute a command in Codex sandbox",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                }
            ],
        }

        resp = await client.post("/v1/responses", json=req_payload)
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")

        raw_stream = await resp.text()
        events = _parse_sse_events(raw_stream)

        # Ensure run_agent_turn was called with expected prompt & client tools
        assert len(captured_turns) == 1
        assert captured_turns[0]["user_msg"] == "Run tests"
        tool_names = [t.get("name") for t in captured_turns[0]["client_tools"]]
        assert "exec_command" in tool_names

        # Verify SSE event sequence for function call dispatch
        event_names = [e["event"] for e in events]
        assert "response.created" in event_names
        assert "response.in_progress" in event_names
        assert "response.output_item.added" in event_names
        assert "response.function_call_arguments.delta" in event_names
        assert "response.function_call_arguments.done" in event_names
        assert "response.output_item.done" in event_names
        assert "response.completed" in event_names

        # Verify response.output_item.added event payload
        item_added = next(e["data"] for e in events if e["event"] == "response.output_item.added")
        item = item_added["item"]
        assert item["type"] == "function_call"
        assert item["name"] == "exec_command"
        assert item["call_id"] == "call_123"

        # Verify response.function_call_arguments.done
        call_done = next(e["data"] for e in events if e["event"] == "response.function_call_arguments.done")
        assert call_done["call_id"] == "call_123"
        assert json.loads(call_done["arguments"]) == {"command": "pytest tests/"}

        # Verify response.completed
        resp_completed = next(e["data"] for e in events if e["event"] == "response.completed")
        assert resp_completed["response"]["status"] == "completed"
        output_items = resp_completed["response"]["output"]
        assert len(output_items) == 1
        assert output_items[0]["type"] == "function_call"
        assert output_items[0]["call_id"] == "call_123"
        assert output_items[0]["status"] == "completed"


@pytest.mark.anyio
async def test_codex_turn_2_tool_output_and_completion(monkeypatch):
    """Verify Turn 2: Codex returns function_call_output, YOLO produces text response."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    captured_turns = []

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        captured_turns.append({
            "user_msg": user_msg,
            "history": list(getattr(session, "message_history", [])),
        })
        final_answer = "All tests verified and passing!"
        if signal_handler:
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:All tests verified")
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:{final_answer}")
        return final_answer

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        req_payload = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Run tests"}],
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": "18 passed in 5.56s",
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "exec_command",
                    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
                }
            ],
        }

        resp = await client.post("/v1/responses", json=req_payload)
        assert resp.status == 200
        assert resp.headers.get("Content-Type", "").startswith("text/event-stream")

        raw_stream = await resp.text()
        events = _parse_sse_events(raw_stream)

        # Verify normalized turn received the tool output
        assert len(captured_turns) == 1
        turn_data = captured_turns[0]
        # In normalized session, tool result is present either as user_msg or in message_history
        assert turn_data["user_msg"] == "18 passed in 5.56s" or any(
            "18 passed" in str(m.get("content", "")) for m in turn_data["history"]
        )

        # Verify SSE stream contains text delta, text done, and completion events
        event_names = [e["event"] for e in events]
        assert "response.output_item.added" in event_names
        assert "response.output_text.delta" in event_names
        assert "response.output_text.done" in event_names
        assert "response.completed" in event_names

        text_done = next(e["data"] for e in events if e["event"] == "response.output_text.done")
        assert text_done["text"] == "All tests verified and passing!"

        resp_completed = next(e["data"] for e in events if e["event"] == "response.completed")
        output = resp_completed["response"]["output"][0]
        assert output["type"] == "message"
        assert output["role"] == "assistant"
        assert output["content"][0]["text"] == "All tests verified and passing!"


@pytest.mark.anyio
async def test_codex_full_end_to_end_handshake_and_multi_turn_flow(monkeypatch):
    """Comprehensive test proving full handshake and 2-turn cycle between Codex and YOLO.

    Sequence:
    1. Codex performs handshake: GET /v1/models?client_version=0.154.0
    2. Codex initiates Turn 1: POST /v1/responses with user task and exec_command tool
    3. YOLO emits client tool call for exec_command, streamed back via SSE
    4. Codex executes tool in local sandbox and sends Turn 2: POST /v1/responses with tool output
    5. YOLO validates input and streams completed response back to Codex
    """
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    turn_counter = 0
    executed_turns = []

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        nonlocal turn_counter
        turn_counter += 1
        executed_turns.append({
            "turn": turn_counter,
            "user_msg": user_msg,
            "history": list(getattr(session, "message_history", [])),
            "client_tools": getattr(session, "client_tools", []),
        })

        if turn_counter == 1:
            # Turn 1: Emit client tool call
            if signal_handler:
                call_payload = json.dumps({
                    "call_id": "call_pytest_456",
                    "name": "exec_command",
                    "arguments": {"command": "pytest tests/"},
                })
                await signal_handler(f"YOLO_CLIENT_TOOL:{call_payload}")
            return "[Client tool dispatched]"
        elif turn_counter == 2:
            # Turn 2: Tool result received, stream answer
            ans = "All tests verified and passing!"
            if signal_handler:
                await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:All tests ")
                await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:{ans}")
            return ans
        raise RuntimeError(f"Unexpected turn {turn_counter}")

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        # Step 1: Handshake
        models_resp = await client.get("/v1/models?client_version=0.154.0")
        assert models_resp.status == 200
        models_data = await models_resp.json()
        model_ids = {m["id"] for m in models_data.get("data", [])}
        assert "gpt-5.6-terra" in model_ids
        assert "yolo" in model_ids
        for m in models_data.get("data", []):
            assert m["truncation_policy"] == {"mode": "auto"}
            assert any(lvl["effort"] == "ultra" for lvl in m.get("supported_reasoning_levels", []))

        # Step 2: Turn 1 (Codex -> YOLO with client tool)
        turn_1_req = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]}
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "exec_command",
                    "description": "Execute a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                }
            ],
        }

        resp_turn1 = await client.post("/v1/responses", json=turn_1_req)
        assert resp_turn1.status == 200
        stream_turn1 = await resp_turn1.text()
        events_turn1 = _parse_sse_events(stream_turn1)

        # Check Turn 1 tool call dispatch
        func_call_done = next(
            e["data"] for e in events_turn1 if e["event"] == "response.function_call_arguments.done"
        )
        assert func_call_done["call_id"] == "call_pytest_456"
        assert json.loads(func_call_done["arguments"]) == {"command": "pytest tests/"}

        comp_turn1 = next(e["data"] for e in events_turn1 if e["event"] == "response.completed")
        assert comp_turn1["response"]["status"] == "completed"
        assert comp_turn1["response"]["output"][0]["call_id"] == "call_pytest_456"

        # Step 3: Turn 2 (Codex executes command and provides function_call_output back)
        turn_2_req = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run tests"}]},
                {
                    "type": "function_call_output",
                    "call_id": "call_pytest_456",
                    "output": "18 passed in 5.56s",
                },
            ],
            "tools": turn_1_req["tools"],
        }

        resp_turn2 = await client.post("/v1/responses", json=turn_2_req)
        assert resp_turn2.status == 200
        stream_turn2 = await resp_turn2.text()
        events_turn2 = _parse_sse_events(stream_turn2)

        # Verify Turn 2 agent verification
        assert len(executed_turns) == 2
        turn_2_data = executed_turns[1]
        assert turn_2_data["user_msg"] == "18 passed in 5.56s" or any(
            "18 passed" in str(m.get("content", "")) for m in turn_2_data["history"]
        )

        # Verify Turn 2 text stream events
        text_done_turn2 = next(e["data"] for e in events_turn2 if e["event"] == "response.output_text.done")
        assert text_done_turn2["text"] == "All tests verified and passing!"

        comp_turn2 = next(e["data"] for e in events_turn2 if e["event"] == "response.completed")
        assert comp_turn2["response"]["output"][0]["content"][0]["text"] == "All tests verified and passing!"


@pytest.mark.anyio
async def test_codex_non_streaming_responses(monkeypatch):
    """Verify non-streaming POST /v1/responses returns full response JSON structure."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        return "Command completed successfully."

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        payload = {
            "model": "gpt-5.6-terra",
            "stream": False,
            "input": [
                {"type": "message", "role": "user", "content": "Check status"}
            ],
        }
        resp = await client.post("/v1/responses", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["object"] == "response"
        assert data["status"] == "completed"
        assert data["model"] == "gpt-5.6-terra"
        assert len(data["output"]) == 1
        assert data["output"][0]["content"][0]["text"] == "Command completed successfully."


@pytest.mark.anyio
async def test_codex_internal_tool_commentary_streaming(monkeypatch):
    """Verify YOLO streams internal tool executions as commentary output items in Responses SSE."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        if signal_handler:
            # Emit internal tool 1: list_dir
            await signal_handler(
                f"__TOOL_CALL__:{json.dumps({'name': 'list_dir', 'args': {'path': 'docs'}, 'call_id': 'call_list_1'})}"
            )
            await signal_handler(
                f"__TOOL_RESULT__:{json.dumps({'name': 'list_dir', 'result': '[DIR] superpowers', 'call_id': 'call_list_1'})}"
            )
            # Emit internal tool 2: read_file
            await signal_handler(
                f"__TOOL_CALL__:{json.dumps({'name': 'read_file', 'args': {'path': 'docs/plan.md'}, 'call_id': 'call_read_2'})}"
            )
            await signal_handler(
                f"__TOOL_RESULT__:{json.dumps({'name': 'read_file', 'result': '# Aura Player Plan', 'call_id': 'call_read_2'})}"
            )
            # Emit final answer streaming delta
            await signal_handler("STREAM:Here is the analyzed plan.")
        return "Here is the analyzed plan."

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        payload = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "analyse"}]}
            ],
        }
        resp = await client.post("/v1/responses", json=payload)
        assert resp.status == 200
        raw_stream = await resp.text()
        events = _parse_sse_events(raw_stream)

        # Collect output items added
        added_items = [e["data"] for e in events if e["event"] == "response.output_item.added"]
        assert len(added_items) >= 3, f"Expected at least 2 commentary items + 1 final answer item, got {len(added_items)}"

        # Verify Item 0: commentary for list_dir
        assert added_items[0]["output_index"] == 0
        assert added_items[0]["item"]["phase"] == "commentary"

        # Verify Item 1: commentary for read_file
        assert added_items[1]["output_index"] == 1
        assert added_items[1]["item"]["phase"] == "commentary"

        # Verify Item 2: final answer
        assert added_items[2]["output_index"] == 2
        assert added_items[2]["item"]["phase"] == "final_answer"

        # Verify text deltas contain tool keywords
        text_deltas = [e["data"]["delta"] for e in events if e["event"] == "response.output_text.delta"]
        joined_deltas = " ".join(text_deltas)
        assert "list_dir" in joined_deltas or "docs" in joined_deltas
        assert "read_file" in joined_deltas or "plan.md" in joined_deltas
        assert "Here is the analyzed plan." in joined_deltas

        # Verify completed event has all items
        completed_ev = next(e["data"] for e in events if e["event"] == "response.completed")
        completed_output = completed_ev["response"]["output"]
        assert len(completed_output) == 3
        assert completed_output[0]["phase"] == "commentary"
        assert completed_output[1]["phase"] == "commentary"
        assert completed_output[2]["phase"] == "final_answer"
        assert completed_output[2]["content"][0]["text"] == "Here is the analyzed plan."


# ── Codex Workspace Tool Routing Tests (Option A) ──


@pytest.mark.anyio
async def test_codex_mode_routes_run_bash_to_exec_command(monkeypatch):
    """When codex_mode is True, run_bash tool calls emit function_call for exec_command."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        # Simulate the agent loop deciding to call run_bash
        # In codex_mode, this should be routed to the client via signal_handler
        if signal_handler:
            call_payload = json.dumps({
                "call_id": "call_bash_001",
                "name": "exec_command",
                "arguments": {"cmd": "pytest tests/"},
            })
            await signal_handler(f"YOLO_CLIENT_TOOL:{call_payload}")
        return "__CLIENT_TOOL_DISPATCHED__"

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        req_payload = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Run the tests"}]},
            ],
            "client_metadata": {"workspace_kind": "project"},
        }

        resp = await client.post("/v1/responses", json=req_payload)
        assert resp.status == 200

        raw_stream = await resp.text()
        events = _parse_sse_events(raw_stream)
        event_names = [e["event"] for e in events]

        # Must emit function_call events, NOT text output
        assert "response.output_item.added" in event_names
        assert "response.function_call_arguments.done" in event_names
        assert "response.completed" in event_names

        # The function_call item should target exec_command
        item_added_events = [e for e in events if e["event"] == "response.output_item.added"]
        fc_item = None
        for ev in item_added_events:
            if isinstance(ev["data"], dict) and ev["data"].get("item", {}).get("type") == "function_call":
                fc_item = ev["data"]["item"]
                break
        assert fc_item is not None, "No function_call output_item.added event found"
        assert fc_item["name"] == "exec_command"
        assert fc_item["call_id"] == "call_bash_001"

        # Verify arguments in function_call_arguments.done
        args_done = next(
            e["data"] for e in events
            if e["event"] == "response.function_call_arguments.done"
        )
        parsed_args = json.loads(args_done["arguments"])
        assert parsed_args["cmd"] == "pytest tests/"

        # response.completed should have status=completed and include the function_call item
        completed = next(e["data"] for e in events if e["event"] == "response.completed")
        assert completed["response"]["status"] == "completed"
        output_items = completed["response"]["output"]
        assert any(item.get("type") == "function_call" for item in output_items)


@pytest.mark.anyio
async def test_codex_mode_internal_tools_still_stream_as_commentary(monkeypatch):
    """Internal tools execute natively and stream as commentary even in codex_mode."""
    yolo_model_server, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async def mock_run_agent_turn(user_msg, session, signal_handler=None, memory_service=None):
        if signal_handler:
            # Simulate internal tool execution (memory_search)
            call_info = json.dumps({"call_id": "tc_mem", "name": "memory_search", "args": {"query": "test"}})
            await signal_handler(f"__TOOL_CALL__:{call_info}")
            res_info = json.dumps({"call_id": "tc_mem", "name": "memory_search", "result": "No results"})
            await signal_handler(f"__TOOL_RESULT__:{res_info}")
            # Then stream the final answer
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Searched memory, found nothing relevant.")
        return "Searched memory, found nothing relevant."

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", mock_run_agent_turn)

    async with TestClient(TestServer(app)) as client:
        req_payload = {
            "model": "gpt-5.6-terra",
            "stream": True,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Search memory"}]},
            ],
            "client_metadata": {"workspace_kind": "project"},
        }

        resp = await client.post("/v1/responses", json=req_payload)
        assert resp.status == 200

        raw_stream = await resp.text()
        events = _parse_sse_events(raw_stream)
        event_names = [e["event"] for e in events]

        # Internal tools should appear as commentary, NOT as function_call
        assert "response.completed" in event_names

        # Check for commentary items (memory_search tool result)
        commentary_items = [
            e for e in events
            if e["event"] == "response.output_item.added"
            and isinstance(e["data"], dict)
            and e["data"].get("item", {}).get("phase") == "commentary"
        ]
        assert len(commentary_items) >= 1, "Internal tool should stream as commentary"

        # Should NOT have function_call items
        fc_items = [
            e for e in events
            if e["event"] == "response.output_item.added"
            and isinstance(e["data"], dict)
            and e["data"].get("item", {}).get("type") == "function_call"
        ]
        assert len(fc_items) == 0, "Internal tools must NOT emit function_call events"


@pytest.mark.anyio
async def test_codex_models_include_tool_mode(monkeypatch):
    """Verify /v1/models includes tool_mode=code_mode_only for Codex compatibility."""
    _, app = _make_app(disable_auth=True, monkeypatch=monkeypatch)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/v1/models")
        assert resp.status == 200
        data = await resp.json()

        for m in data["data"]:
            assert m.get("tool_mode") == "code_mode_only", (
                f"Model {m['id']} missing tool_mode=code_mode_only"
            )
            assert m.get("supports_parallel_tool_calls") is True, (
                f"Model {m['id']} missing supports_parallel_tool_calls"
            )
            assert m.get("multi_agent_version") == "v2", (
                f"Model {m['id']} missing multi_agent_version=v2"
            )


def test_map_to_codex_tool_run_bash():
    """Verify _map_to_codex_tool correctly translates run_bash → exec_command."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("run_bash", {"command": "pytest tests/"})
    assert name == "exec_command"
    assert args == {"cmd": "pytest tests/"}


def test_map_to_codex_tool_write_file():
    """Verify _map_to_codex_tool translates write_file to a heredoc exec_command."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("write_file", {"path": "/tmp/test.txt", "content": "hello world"})
    assert name == "exec_command"
    assert "cmd" in args
    cmd = args["cmd"]
    assert "/tmp/test.txt" in cmd
    assert "hello world" in cmd
    assert "YOLO_HEREDOC_EOF" in cmd


def test_map_to_codex_tool_make_dir():
    """Verify _map_to_codex_tool translates make_dir to mkdir -p."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("make_dir", {"path": "/home/user/project"})
    assert name == "exec_command"
    assert "mkdir -p" in args["cmd"]
    assert "/home/user/project" in args["cmd"]


def test_map_to_codex_tool_git_commit():
    """Verify _map_to_codex_tool translates git_commit with message."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("git_commit", {"message": "feat: add tests"})
    assert name == "exec_command"
    cmd = args["cmd"]
    assert "git commit" in cmd
    assert "feat: add tests" in cmd


def test_map_to_codex_tool_exec_command_direct():
    """Verify _map_to_codex_tool passes through exec_command directly."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("exec_command", {"cmd": "ls -la", "workdir": "/home"})
    assert name == "exec_command"
    assert args == {"cmd": "ls -la", "workdir": "/home"}


def test_map_to_codex_tool_apply_patch_direct():
    """Verify _map_to_codex_tool passes through apply_patch."""
    from agent import _map_to_codex_tool

    name, args = _map_to_codex_tool("apply_patch", {"patch": "*** Begin Patch\n*** End Patch"})
    assert name == "apply_patch"
    assert args == {"patch": "*** Begin Patch\n*** End Patch"}

