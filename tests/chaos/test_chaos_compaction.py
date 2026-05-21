import pytest
from unittest.mock import AsyncMock, MagicMock
from session import Session
from prompt_builder import _compact_history

@pytest.mark.asyncio
async def test_compact_history_short():
    session = Session(user_id=1, message_history=[{"role": "user", "content": "hi"}] * 5)
    router = AsyncMock()
    await _compact_history(session, router)
    assert len(session.message_history) == 5
    router.chat_completions.assert_not_called()

@pytest.mark.asyncio
async def test_compact_history_tool_sequence_safety():
    # History: System, User, Assistant (call), Tool (result), Assistant (call), Tool (result), User (new)
    history = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "r1"},
        {"role": "assistant", "content": "a2", "tool_calls": [{"id": "t2"}]},
        {"role": "tool", "tool_call_id": "t2", "content": "r2"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a4"},
        {"role": "user", "content": "u4"},
        {"role": "assistant", "content": "a5"},
    ]
    session = Session(user_id=1, message_history=list(history))
    
    router = AsyncMock()
    # Mock LLM response
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "Summary of conversation"
    router.chat_completions.return_value = resp
    
    await _compact_history(session, router)
    
    # Check that it kept at least 6 messages AND stopped at a user message
    # Last messages: u4, a5 (2)
    # Walk back from -6:
    # -6 is u2. Stop!
    # So keep_last should be 6.
    # New history: System, Summary, [u2, a3, u3, a4, u4, a5]
    assert session.message_history[0]["role"] == "system"
    assert "[CONVERSATION_SUMMARY]" in session.message_history[1]["content"]
    assert session.message_history[2]["role"] == "user"
    assert session.message_history[2]["content"] == "u2"

@pytest.mark.asyncio
async def test_compact_history_no_system_prompt():
    history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
    session = Session(user_id=1, message_history=list(history))
    
    router = AsyncMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "Summary"
    router.chat_completions.return_value = resp
    
    await _compact_history(session, router)
    
    assert session.message_history[0]["role"] == "assistant"
    assert "[CONVERSATION_SUMMARY]" in session.message_history[0]["content"]

@pytest.mark.asyncio
async def test_compact_history_llm_failure():
    history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
    session = Session(user_id=1, message_history=list(history))
    
    router = AsyncMock()
    router.chat_completions.side_effect = Exception("LLM Down")
    
    await _compact_history(session, router)
    
    # History should remain unchanged on failure
    assert len(session.message_history) == 15

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_compact_history_short())
    print("test_compact_history_short passed")
    asyncio.run(test_compact_history_tool_sequence_safety())
    print("test_compact_history_tool_sequence_safety passed")
    asyncio.run(test_compact_history_no_system_prompt())
    print("test_compact_history_no_system_prompt passed")
    asyncio.run(test_compact_history_llm_failure())
    print("test_compact_history_llm_failure passed")
    print("All compaction chaos tests passed!")
