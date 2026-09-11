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


def _make_app(disable_auth: bool = True):
    if disable_auth:
        os.environ["YOLO_MODEL_DISABLE_AUTH"] = "true"
    else:
        os.environ["YOLO_MODEL_DISABLE_AUTH"] = "false"
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
async def test_codex_models_handshake_endpoint():
    """Verify GET /v1/models?client_version=0.154.0 conforms to Codex specification."""
    yolo_model_server, app = _make_app(disable_auth=True)

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
    yolo_model_server, app = _make_app(disable_auth=True)

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
    yolo_model_server, app = _make_app(disable_auth=True)

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
    yolo_model_server, app = _make_app(disable_auth=True)

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
    yolo_model_server, app = _make_app(disable_auth=True)

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
