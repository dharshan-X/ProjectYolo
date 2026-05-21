import pytest
from tool_dispatcher import sanitize_history

def test_sanitize_valid():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "res"},
        {"role": "assistant", "content": "done"}
    ]
    sanitized = sanitize_history(history)
    assert sanitized == history

def test_sanitize_orphaned_tool():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "t1", "content": "res"},
        {"role": "assistant", "content": "done"}
    ]
    sanitized = sanitize_history(history)
    # Orphaned tool response should be dropped
    assert len(sanitized) == 2
    assert sanitized[1]["role"] == "assistant"

def test_sanitize_missing_tool_response():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [{"id": "t1"}, {"id": "t2"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "res1"},
        # t2 missing
        {"role": "assistant", "content": "done"}
    ]
    sanitized = sanitize_history(history)
    # Sequence broken. Assistant tool_calls should be stripped.
    assert "tool_calls" not in sanitized[1]
    assert "[Corrupted tool call sequence removed for safety]" in sanitized[1]["content"]
    # Tool response for t1 should be dropped because sequence is broken
    assert len(sanitized) == 3
    assert sanitized[2]["content"] == "done"

def test_sanitize_mismatched_ids():
    history = [
        {"role": "assistant", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t2", "content": "res"}
    ]
    sanitized = sanitize_history(history)
    assert "tool_calls" not in sanitized[0]
    assert len(sanitized) == 1

if __name__ == "__main__":
    test_sanitize_valid()
    print("test_sanitize_valid passed")
    test_sanitize_orphaned_tool()
    print("test_sanitize_orphaned_tool passed")
    test_sanitize_missing_tool_response()
    print("test_sanitize_missing_tool_response passed")
    test_sanitize_mismatched_ids()
    print("test_sanitize_mismatched_ids passed")
    print("All sanitize chaos tests passed!")
