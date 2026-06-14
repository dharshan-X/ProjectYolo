import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from session import Session
from tool_dispatcher import execute_tool_direct
from prompt_builder import _compact_history

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
        func_args='{invalid json}',
        user_id=1,
    )
    assert "Error: Arguments for dummy_tool must be a JSON object" in res

@pytest.mark.anyio
async def test_compact_history(mock_session):
    mock_router = MagicMock()
    mock_router.chat_completions = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="compacted summary"))]
    ))
    
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
    
    with patch("agent._compact_history", new_callable=AsyncMock) as mock_compact:
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
            side_effect=[
                Exception("context_length_exceeded"),
                mock_generator()
            ]
        )
        
        with patch("agent.router", mock_router):
            res, err = await _stream_llm_round(mock_session, [], None)
            
            assert err is None
            assert res["content"] == "retry success"
            mock_compact.assert_called_once_with(mock_session, mock_router)


@pytest.mark.anyio
async def test_request_zipping(mock_session):
    from agent import zip_history_payload
    import os
    
    # Configure limits via environment
    os.environ["REQUEST_ZIPPING"] = "true"
    os.environ["REQUEST_ZIPPING_THRESHOLD"] = "50"
    os.environ["REQUEST_ZIPPING_KEEP_HEAD"] = "20"
    os.environ["REQUEST_ZIPPING_KEEP_TAIL"] = "15"
    
    long_content = "A" * 100
    mock_session.message_history = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": long_content}
    ]
    
    zipped = zip_history_payload(mock_session.message_history, mock_session)
    
    # Original message history should NOT be changed
    assert mock_session.message_history[1]["content"] == long_content
    
    # Zipped content should be truncated and contain the correct prefix/suffix/marker
    zipped_content = zipped[1]["content"]
    assert "REQUEST ZIPPED" in zipped_content
    assert zipped_content.startswith("A" * 20)
    assert zipped_content.endswith("A" * 15)


