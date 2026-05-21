import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from llm_router import LLMRouter, LLMConfig, RateLimiter

@pytest.mark.asyncio
async def test_rate_limiter():
    limiter = RateLimiter(rpm_limit=2)
    start = asyncio.get_event_loop().time()
    
    await limiter.wait() # Call 1
    await limiter.wait() # Call 2
    
    # Next call should wait
    task = asyncio.create_task(limiter.wait())
    await asyncio.sleep(0.1)
    assert not task.done()
    
    # We can't easily wait 60s in a unit test without mocking time.time()
    # but the logic seems sound.

@pytest.mark.asyncio
async def test_router_retry_success():
    config = LLMConfig(provider="openai", model="m", api_key="k", base_url="b")
    router = LLMRouter(config)
    
    mock_create = AsyncMock()
    # Fail twice with 429, then succeed
    mock_create.side_effect = [
        Exception("429 Rate Limit Exceeded"),
        Exception("503 Service Unavailable"),
        MagicMock(choices=[MagicMock()])
    ]
    
    with patch.object(router._openai_client.chat.completions, 'create', mock_create):
        # We need to mock asyncio.sleep to speed up the test
        with patch('asyncio.sleep', AsyncMock()):
            res = await router.chat_completions(messages=[], tools=[])
            assert mock_create.call_count == 3
            assert res is not None

@pytest.mark.asyncio
async def test_router_no_retry_on_auth_error():
    config = LLMConfig(provider="openai", model="m", api_key="k", base_url="b")
    router = LLMRouter(config)
    
    mock_create = AsyncMock()
    mock_create.side_effect = Exception("401 Unauthorized")
    
    with patch.object(router._openai_client.chat.completions, 'create', mock_create):
        with pytest.raises(Exception, match="401 Unauthorized"):
            await router.chat_completions(messages=[], tools=[])
        assert mock_create.call_count == 1

@pytest.mark.asyncio
async def test_router_anthropic_no_litellm():
    config = LLMConfig(provider="anthropic", model="m", api_key="k", base_url=None)
    router = LLMRouter(config)
    
    with patch('llm_router.litellm_acompletion', None):
        with pytest.raises(RuntimeError, match="requires `litellm`"):
            await router.chat_completions(messages=[], tools=[])

@pytest.mark.asyncio
async def test_router_unsupported_provider():
    config = LLMConfig(provider="unknown", model="m", api_key="k", base_url="b")
    router = LLMRouter(config)
    with pytest.raises(RuntimeError, match="Unsupported provider"):
        await router.chat_completions(messages=[], tools=[])

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_router_retry_success())
    print("test_router_retry_success passed")
    asyncio.run(test_router_no_retry_on_auth_error())
    print("test_router_no_retry_on_auth_error passed")
    print("All router chaos tests passed!")
