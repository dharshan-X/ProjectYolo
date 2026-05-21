import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch
from tool_dispatcher import execute_tool_direct
from tools.registry import register_tool, TOOL_REGISTRY

# Define some test tools
@register_tool("chaos_success")
def chaos_success(arg1, arg2="default"):
    return f"Success: {arg1}, {arg2}"

@register_tool("chaos_error")
def chaos_error():
    raise ValueError("Chaos error happened")

@register_tool("chaos_return_non_str")
def chaos_return_non_str():
    return {"status": "ok", "value": 42}

@register_tool("chaos_transient_error")
def chaos_transient_error():
    global retry_count
    retry_count += 1
    if retry_count < 2:
        raise OSError("Transient failure")
    return "Recovered"

retry_count = 0

@pytest.mark.asyncio
async def test_dispatcher_success():
    res = await execute_tool_direct("chaos_success", {"arg1": "hello"}, user_id=123)
    assert res == "Success: hello, default"

@pytest.mark.asyncio
async def test_dispatcher_json_args():
    res = await execute_tool_direct("chaos_success", '{"arg1": "json"}', user_id=123)
    assert res == "Success: json, default"

@pytest.mark.asyncio
async def test_dispatcher_invalid_json():
    res = await execute_tool_direct("chaos_success", '{"arg1": "json"', user_id=123)
    assert "Error: Arguments" in res

@pytest.mark.asyncio
async def test_dispatcher_not_found():
    res = await execute_tool_direct("non_existent_tool", {}, user_id=123)
    assert "Error: non_existent_tool not found" in res

@pytest.mark.asyncio
async def test_dispatcher_exception():
    res = await execute_tool_direct("chaos_error", {}, user_id=123)
    assert "Error in chaos_error: Chaos error happened" in res

@pytest.mark.asyncio
async def test_dispatcher_non_str_return():
    res = await execute_tool_direct("chaos_return_non_str", {}, user_id=123)
    # The dispatcher should convert it to string
    assert res == str({"status": "ok", "value": 42})

@pytest.mark.asyncio
async def test_dispatcher_retry():
    global retry_count
    retry_count = 0
    res = await execute_tool_direct("chaos_transient_error", {}, user_id=123)
    assert res == "Recovered"
    assert retry_count == 2

@pytest.mark.asyncio
async def test_dispatcher_injection():
    @register_tool("chaos_injection")
    def chaos_injection(user_id, confirm_func):
        return f"Injected: {user_id}"
    
    res = await execute_tool_direct("chaos_injection", {}, user_id=123)
    assert res == "Injected: 123"

if __name__ == "__main__":
    # Manual test run
    async def run_tests():
        await test_execute_tool_success()
        print("test_execute_tool_success passed")
        await test_execute_tool_json_args()
        print("test_execute_tool_json_args passed")
        await test_execute_tool_invalid_json()
        print("test_execute_tool_invalid_json passed")
        await test_execute_tool_not_found()
        print("test_execute_tool_not_found passed")
        await test_execute_tool_exception()
        print("test_execute_tool_exception passed")
        await test_execute_tool_non_str_return()
        print("test_execute_tool_non_str_return passed")
        await test_execute_tool_retry()
        print("test_execute_tool_retry passed")
        await test_execute_tool_injection()
        print("test_execute_tool_injection passed")
        print("All dispatcher chaos tests passed!")

    asyncio.run(run_tests())
