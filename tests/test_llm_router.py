from unittest.mock import AsyncMock, patch

import pytest

from llm_router import LLMConfig, LLMRouter, load_llm_config

_ROUTER_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "MODEL_NAME",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
)


@pytest.fixture(autouse=True)
def clear_router_environment(monkeypatch):
    for variable in _ROUTER_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)


class StatusError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def compatible_router():
    return LLMRouter(
        LLMConfig(
            provider="compatible",
            model="test-model",
            api_key=None,
            base_url="http://localhost:1234/v1",
        )
    )


def test_load_config_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery-provider")

    with pytest.raises(
        ValueError, match=r"Unsupported LLM_PROVIDER 'mystery-provider'.*openai"
    ):
        load_llm_config()


def test_openrouter_never_uses_openai_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = load_llm_config()

    assert config.api_key is None
    with pytest.raises(
        RuntimeError,
        match=r"OPENROUTER_API_KEY is required for provider `openrouter`",
    ):
        LLMRouter(config)


def test_openai_requires_openai_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "compatible-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")

    config = load_llm_config()

    assert config.api_key is None
    with pytest.raises(
        RuntimeError,
        match=r"OPENAI_API_KEY is required for provider `openai`",
    ):
        LLMRouter(config)


def test_compatible_uses_only_llm_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LLM_API_KEY", "compatible-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = load_llm_config()

    assert config.api_key == "compatible-key"


def test_compatible_may_be_keyless_without_openai_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = load_llm_config()
    router = LLMRouter(config)

    assert config.api_key is None
    assert router._openai_client is not None


def test_auto_with_openai_key_remains_official_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("LLM_API_KEY", "compatible-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")

    config = load_llm_config()

    assert config.provider == "openai"
    assert config.api_key == "openai-key"
    assert config.base_url == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_streaming_router_does_not_retry_transient_errors():
    router = compatible_router()
    call = AsyncMock(side_effect=StatusError(503, "Service unavailable"))
    router._chat_completions_inner = call

    with patch("llm_router.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(StatusError):
            await router.chat_completions(messages=[], tools=[], stream=True)

    call.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_streaming_router_retries_up_to_three_attempts():
    router = compatible_router()
    call = AsyncMock(
        side_effect=[
            StatusError(429, "Rate limited"),
            StatusError(503, "Service unavailable"),
            "success",
        ]
    )
    router._chat_completions_inner = call

    with patch("llm_router.asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = await router.chat_completions(messages=[], tools=[], stream=False)

    assert result == "success"
    assert call.await_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_structured_status_code_takes_precedence_over_message():
    router = compatible_router()
    call = AsyncMock(
        side_effect=[
            StatusError(503, "400 Bad Request"),
            "success",
        ]
    )
    router._chat_completions_inner = call

    with patch("llm_router.asyncio.sleep", new_callable=AsyncMock):
        result = await router.chat_completions(messages=[], tools=[])

    assert result == "success"
    assert call.await_count == 2


@pytest.mark.asyncio
async def test_400_message_mentioning_500_is_not_retried():
    router = compatible_router()
    call = AsyncMock(side_effect=Exception("400 Bad Request: max 500 tokens"))
    router._chat_completions_inner = call

    with patch("llm_router.asyncio.sleep", new_callable=AsyncMock) as sleep:
        with pytest.raises(Exception, match="400 Bad Request"):
            await router.chat_completions(messages=[], tools=[])

    call.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_errors_remain_retryable():
    router = compatible_router()
    call = AsyncMock(side_effect=[ConnectionResetError("connection reset"), "success"])
    router._chat_completions_inner = call

    with patch("llm_router.asyncio.sleep", new_callable=AsyncMock):
        result = await router.chat_completions(messages=[], tools=[])

    assert result == "success"
    assert call.await_count == 2
