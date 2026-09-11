"""Tests for yolo_model_server — OpenAI compat layer for Claude Code / Codex."""
import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp.test_utils import TestClient, TestServer


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_app(disable_auth=True):
    if disable_auth:
        os.environ["YOLO_MODEL_DISABLE_AUTH"] = "true"
    else:
        os.environ["YOLO_MODEL_DISABLE_AUTH"] = "false"
    import importlib
    import yolo_model_server
    importlib.reload(yolo_model_server)
    app = yolo_model_server.create_app()
    return yolo_model_server, app


async def _make_client(app):
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.mark.anyio
async def test_list_models_no_auth_required():
    yolo_model_server, app = _make_app(disable_auth=True)
    client = await _make_client(app)
    try:
        resp = await client.get("/v1/models")
        assert resp.status == 200
        data = await resp.json()
        assert data["object"] == "list"
        ids = {m["id"] for m in data["data"]}
        assert "yolo" in ids
        assert "yolo-think" in ids
    finally:
        await client.close()


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


@pytest.mark.anyio
async def test_health_no_auth():
    yolo_model_server, app = _make_app(disable_auth=True)
    client = await _make_client(app)
    try:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert "model" in data
    finally:
        await client.close()


@pytest.mark.anyio
async def test_chat_completions_requires_messages():
    yolo_model_server, app = _make_app(disable_auth=True)
    client = await _make_client(app)
    try:
        resp = await client.post("/v1/chat/completions", json={"model": "yolo", "messages": []})
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data
    finally:
        await client.close()


@pytest.mark.anyio
async def test_chat_completions_invalid_json():
    yolo_model_server, app = _make_app(disable_auth=True)
    client = await _make_client(app)
    try:
        resp = await client.post("/v1/chat/completions", data="not-json", headers={"Content-Type": "application/json"})
        assert resp.status == 400
    finally:
        await client.close()


@pytest.mark.anyio
async def test_chat_completions_non_stream_success(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=True)
    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", AsyncMock(return_value="Hello from Yolo"))

    client = await _make_client(app)
    try:
        payload = {"model": "yolo", "messages": [{"role": "user", "content": "hi"}]}
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "yolo"
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["message"]["content"] == "Hello from Yolo"
        assert "usage" in data
        assert data["choices"][0]["finish_reason"] == "stop"
    finally:
        await client.close()


@pytest.mark.anyio
async def test_chat_completions_stream_success(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=True)

    async def fake_run(user_msg, session, signal_handler=None, memory_service=None):
        if signal_handler:
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Hello ")
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Hello from")
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Hello from Yolo")
        return "Hello from Yolo"

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", fake_run)

    client = await _make_client(app)
    try:
        payload = {"model": "yolo", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        text = await resp.text()
        assert "data:" in text
        assert "[DONE]" in text
        assert "Hello" in text
    finally:
        await client.close()


@pytest.mark.anyio
async def test_chat_completions_auth_required_when_enabled(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=False)
    monkeypatch.setenv("YOLO_MODEL_API_KEYS", "secret123")
    monkeypatch.setattr(yolo_model_server, "_get_allowed_keys", lambda: ["secret123"])

    client = await _make_client(app)
    try:
        payload = {"model": "yolo", "messages": [{"role": "user", "content": "hi"}]}

        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status == 401

        resp = await client.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer wrong"})
        assert resp.status == 401

        monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", AsyncMock(return_value="ok"))
        resp = await client.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer secret123"})
        assert resp.status == 200
    finally:
        await client.close()


@pytest.mark.anyio
async def test_anthropic_messages_non_stream(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=True)
    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", AsyncMock(return_value="Anthropic hello"))

    client = await _make_client(app)
    try:
        payload = {"model": "yolo", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]}
        resp = await client.post("/v1/messages", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["type"] == "message"
        assert data["role"] == "assistant"
        assert data["content"][0]["text"] == "Anthropic hello"
        assert data["stop_reason"] == "end_turn"
    finally:
        await client.close()


@pytest.mark.anyio
async def test_anthropic_messages_stream(monkeypatch):
    yolo_model_server, app = _make_app(disable_auth=True)

    async def fake_run(user_msg, session, signal_handler=None, memory_service=None):
        if signal_handler:
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Hi ")
            await signal_handler(f"{yolo_model_server.yolo_agent.TUIMessage.STREAM}:Hi there")
        return "Hi there"

    monkeypatch.setattr(yolo_model_server.yolo_agent, "run_agent_turn", fake_run)

    client = await _make_client(app)
    try:
        payload = {"model": "yolo", "messages": [{"role": "user", "content": "hi"}], "stream": True}
        resp = await client.post("/v1/messages", json=payload)
        assert resp.status == 200
        text = await resp.text()
        assert "content_block_delta" in text
        assert "message_stop" in text
    finally:
        await client.close()


def test_build_yolo_session_model_aliases():
    yolo_model_server, _ = _make_app(disable_auth=True)
    s, _ = yolo_model_server._build_yolo_session(user_id=1, incoming_messages=[{"role": "user", "content": "hi"}], model_name="yolo")
    assert s.yolo_mode is True
    assert s.think_mode is False

    s2, _ = yolo_model_server._build_yolo_session(user_id=1, incoming_messages=[{"role": "user", "content": "hi"}], model_name="yolo-think")
    assert s2.think_mode is True

    s3, _ = yolo_model_server._build_yolo_session(user_id=1, incoming_messages=[{"role": "user", "content": "hi"}], model_name="yolo-safe")
    assert s3.yolo_mode is False


def test_normalize_incoming_messages():
    yolo_model_server, _ = _make_app(disable_auth=True)
    raw = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    norm = yolo_model_server._normalize_incoming_messages(raw)
    assert norm[0]["content"] == "hello"
    assert norm[1]["content"] == "hi"


def test_api_key_to_user_id_deterministic():
    yolo_model_server, _ = _make_app(disable_auth=True)
    a = yolo_model_server._api_key_to_user_id("yolo-local")
    b = yolo_model_server._api_key_to_user_id("yolo-local")
    assert a == b
    assert 1 <= a <= 2000001


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

