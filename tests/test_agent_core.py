from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prompt_builder import _compact_history
from session import Session
from tool_dispatcher import execute_tool_direct


@pytest.fixture
def mock_session():
    return Session(user_id=1, message_history=[])


@pytest.mark.anyio
async def test_execute_tool_direct_valid_json():
    with patch("tools.registry.TOOL_REGISTRY") as mock_registry:
        mock_target = AsyncMock(return_value="tool output")
        mock_registry.get.return_value = mock_target

        res = await execute_tool_direct(
            func_name="dummy_tool",
            func_args='{"arg1": "value"}',
            user_id=1,
        )
        assert res == "tool output"
        mock_target.assert_called_once()


@pytest.mark.anyio
async def test_execute_tool_direct_invalid_json():
    res = await execute_tool_direct(
        func_name="dummy_tool",
        func_args="{invalid json}",
        user_id=1,
    )
    assert "Error: Arguments for dummy_tool must be a JSON object" in res


@pytest.mark.anyio
async def test_compact_history(mock_session):
    mock_router = MagicMock()
    mock_router.chat_completions = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="compacted summary"))]
        )
    )

    # Needs more than 10 messages to trigger compaction
    mock_session.message_history = [{"role": "system", "content": "mock system"}] + [
        {"role": "user", "content": f"msg {i}"} for i in range(11)
    ]

    await _compact_history(mock_session, mock_router)

    # First message should be system, second should be the compacted summary
    assert mock_session.message_history[0]["role"] == "system"
    assert mock_session.message_history[1]["role"] == "assistant"
    assert "compacted summary" in mock_session.message_history[1]["content"]
    assert len(mock_session.message_history) == 8


@pytest.mark.anyio
async def test_context_overflow_retry(mock_session):
    from agent import _stream_llm_round

    mock_session.message_history = [{"role": "system", "content": "mock system"}] + [
        {"role": "user", "content": f"msg {i}"} for i in range(11)
    ]

    async def compact_history(session, _router):
        session.message_history = [
            session.message_history[0],
            session.message_history[-1],
        ]

    with patch(
        "agent._compact_history", new_callable=AsyncMock, side_effect=compact_history
    ) as mock_compact:
        mock_router = MagicMock()

        class MockDelta:
            def __init__(self, content):
                self.content = content
                self.reasoning_content = None
                self.tool_calls = None

        class MockChoice:
            def __init__(self, content):
                self.delta = MockDelta(content)

        class MockChunk:
            def __init__(self, content):
                self.choices = [MockChoice(content)]

        async def mock_generator():
            yield MockChunk("retry success")

        mock_router.chat_completions = AsyncMock(
            side_effect=[Exception("context_length_exceeded"), mock_generator()]
        )

        with patch("agent.router", mock_router):
            res, err = await _stream_llm_round(mock_session, [], None)

            assert err is None
            assert res["content"] == "retry success"
            mock_compact.assert_called_once_with(mock_session, mock_router)


@pytest.mark.anyio
async def test_request_zipping_preserves_authoritative_messages(
    mock_session, monkeypatch
):
    from agent import zip_history_payload

    monkeypatch.setenv("REQUEST_ZIPPING", "true")
    monkeypatch.setenv("REQUEST_ZIPPING_THRESHOLD", "50")
    monkeypatch.setenv("REQUEST_ZIPPING_KEEP_HEAD", "20")
    monkeypatch.setenv("REQUEST_ZIPPING_KEEP_TAIL", "15")

    long_system = "S" * 100
    long_tool_result = "A" * 100
    long_user_request = "U" * 100
    mock_session.message_history = [
        {"role": "system", "content": long_system},
        {"role": "tool", "content": long_tool_result},
        {"role": "user", "content": long_user_request},
    ]

    zipped = zip_history_payload(mock_session.message_history, mock_session)

    assert mock_session.message_history[1]["content"] == long_tool_result
    assert zipped[0]["content"] == long_system
    assert zipped[2]["content"] == long_user_request
    zipped_content = zipped[1]["content"]
    assert "REQUEST ZIPPED" in zipped_content
    assert zipped_content.startswith("A" * 20)
    assert zipped_content.endswith("A" * 15)


def test_session_save_behavior(mock_session):
    from session import SessionManager

    with patch("session.save_session") as mock_save:
        sm = SessionManager()
        # Add the mock session to the manager
        sm.sessions[1] = mock_session

        # Initial save should call save_session because last_saved_signature is None
        sm.save(1)
        assert mock_save.call_count == 1
        mock_save.reset_mock()

        # history_dirty is set to False after save, and signature is recorded.
        # Calling save again without changes should NOT trigger save_session.
        sm.save(1)
        assert mock_save.call_count == 0

        # Now let's mark it dirty but NOT change the signature.
        # This simulates a redundant call where history_dirty was somehow set
        # or just verifying the optimization check logic.
        # Wait, if history_dirty is True, save will be called even if signature is same.
        # Let's test that.
        sm.sessions[1].mark_dirty()
        sm.save(1)
        assert mock_save.call_count == 1
        mock_save.reset_mock()

        # Let's test signature change
        sm.sessions[1].message_history.append({"role": "user", "content": "hello"})
        # Not explicitly marking dirty just to test if save skips if history_dirty is False
        # but signature is different.
        # Wait, if history_dirty is False, it will skip if signature matches.
        # If signature differs, it will save.
        sm.save(1)
        assert mock_save.call_count == 1
