import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from session import Session
from agent import run_agent_turn, resolve_confirmations, PendingConfirmationError
from prompt_builder import get_initial_messages

@pytest.fixture
def mock_router():
    router = AsyncMock()
    return router

@pytest.mark.asyncio
async def test_hitl_flow(mock_router):
    session = Session(user_id=1, yolo_mode=False)
    
    # Mock LLM to call write_file (destructive) via stream
    async def mock_stream():
        # First chunk: tool call start
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock(content=None, tool_calls=[
            MagicMock(index=0, id="tc1", function=MagicMock(name="write_file", arguments='{"path": "test.txt", '))
        ])
        chunk1.choices[0].delta.model_dump.return_value = {} # Simplified
        # We need model_dump to return the dict structure for _deep_merge
        chunk1.choices[0].delta.tool_calls[0].model_dump.return_value = {
            "index": 0, "id": "tc1", "function": {"name": "write_file", "arguments": '{"path": "test.txt", '}
        }
        yield chunk1
        
        # Second chunk: tool call end
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock(content=None, tool_calls=[
            MagicMock(index=0, function=MagicMock(arguments=' "content": "hello"}'))
        ])
        chunk2.choices[0].delta.tool_calls[0].model_dump.return_value = {
            "index": 0, "function": {"arguments": ' "content": "hello"}'}
        }
        yield chunk2
        
        # Third chunk: usage
        chunk3 = MagicMock()
        chunk3.choices = []
        chunk3.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        yield chunk3

    mock_router.chat_completions.return_value = mock_stream()
    
    # 1. Run turn - should raise PendingConfirmationError
    with patch('agent.router', mock_router):
        with pytest.raises(PendingConfirmationError) as excinfo:
            await run_agent_turn("write something", session)
        
        assert excinfo.value.action == "write_file"
        assert len(session.pending_confirmations) == 1
        assert session.message_history[-1]["content"] == "[HITL_PENDING]"

    # 2. Resolve confirmation
    # Mock LLM response for the turn AFTER resolution (streaming "Done!")
    async def mock_stream_done():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock(content="Done!", tool_calls=None)
        yield chunk
        chunk_usage = MagicMock()
        chunk_usage.choices = []
        chunk_usage.usage = MagicMock(prompt_tokens=5, completion_tokens=2, total_tokens=7)
        yield chunk_usage

    mock_router.chat_completions.return_value = mock_stream_done()
    
    # Mock execute_tool_direct to succeed
    with patch('agent.execute_tool_direct', AsyncMock(return_value="Successfully wrote to 'test.txt'.")) as mock_exec:
        with patch('agent.router', mock_router):
            result = await resolve_confirmations(session, user_id=1, confirm_all=True)
            
            assert result == "Done!"
            assert len(session.pending_confirmations) == 0
            # History should have the real result now
            tool_msg = next(m for m in reversed(session.message_history) if m.get("role") == "tool" and m.get("tool_call_id") == "tc1")
            assert "Successfully wrote" in tool_msg["content"]

@pytest.mark.asyncio
async def test_hitl_mixed_safety(mock_router):
    session = Session(user_id=1, yolo_mode=False)
    
    # Mock LLM to call write_file (HITL) AND read_file (Safe)
    async def mock_stream_mixed():
        # TC1: write_file (destructive)
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta = MagicMock(content=None, tool_calls=[
            MagicMock(index=0, id="tc1", function=MagicMock(name="write_file", arguments='{"path": "a.txt", "content": "x"}'))
        ])
        chunk1.choices[0].delta.tool_calls[0].model_dump.return_value = {
            "index": 0, "id": "tc1", "function": {"name": "write_file", "arguments": '{"path": "a.txt", "content": "x"}'}
        }
        yield chunk1
        
        # TC2: read_file (safe)
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta = MagicMock(content=None, tool_calls=[
            MagicMock(index=1, id="tc2", function=MagicMock(name="read_file", arguments='{"path": "b.txt"}'))
        ])
        chunk2.choices[0].delta.tool_calls[0].model_dump.return_value = {
            "index": 1, "id": "tc2", "function": {"name": "read_file", "arguments": '{"path": "b.txt"}'}
        }
        yield chunk2
        
        chunk3 = MagicMock()
        chunk3.choices = []
        chunk3.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        yield chunk3

    mock_router.chat_completions.return_value = mock_stream_mixed()
    
    with patch('agent.router', mock_router):
        with patch('agent.execute_tool_direct', AsyncMock(return_value="file content")) as mock_exec:
            with pytest.raises(PendingConfirmationError):
                await run_agent_turn("do both", session)
            
            # read_file should have been executed
            # write_file should be pending
            assert len(session.pending_confirmations) == 1
            assert session.pending_confirmations[0]["action"] == "write_file"
            
            tool_msgs = [m for m in session.message_history if m.get("role") == "tool"]
            # Verify read_file was executed (content is "file content")
            assert any(m["name"] == "read_file" and m["content"] == "file content" for m in tool_msgs)
            # Verify write_file is pending
            assert any(m["name"] == "write_file" and m["content"] == "[HITL_PENDING]" for m in tool_msgs)

if __name__ == "__main__":
    import asyncio
    # Manual run logic
    pass
