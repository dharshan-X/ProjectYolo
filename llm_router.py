from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

try:
    from litellm import acompletion as litellm_acompletion
except Exception:
    litellm_acompletion = None

import asyncio
import random
import threading
import time


class RateLimiter:
    def __init__(self, rpm_limit: int):
        self.rpm_limit = rpm_limit
        self.period = 60.0
        self.calls: list[float] = []
        self._lock = threading.Lock()

    async def wait(self):
        if self.rpm_limit <= 0:
            return

        while True:
            with self._lock:
                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period]
                if len(self.calls) < self.rpm_limit:
                    self.calls.append(now)
                    return
                sleep_time = self.period - (now - self.calls[0])
            # Sleep OUTSIDE the lock
            import sys

            sys.stdout.write(
                f"\n[Rate Limit] Reached limit of {self.rpm_limit} requests/min. Pausing for {sleep_time:.1f}s to prevent exhaustion...\n"
            )
            sys.stdout.flush()
            await asyncio.sleep(sleep_time)


_GLOBAL_RATE_LIMITER: Optional[RateLimiter] = None


def _get_rate_limiter() -> RateLimiter:
    global _GLOBAL_RATE_LIMITER
    try:
        rpm = int(os.getenv("LLM_RPM_LIMIT", "40"))
    except ValueError:
        rpm = 40
    if _GLOBAL_RATE_LIMITER is None:
        _GLOBAL_RATE_LIMITER = RateLimiter(rpm_limit=rpm)
    elif _GLOBAL_RATE_LIMITER.rpm_limit != rpm:
        _GLOBAL_RATE_LIMITER.rpm_limit = rpm
    return _GLOBAL_RATE_LIMITER


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: Optional[str]
    base_url: Optional[str]

    def supports_vision(self) -> bool:
        """Check if the configured model natively supports vision."""
        m = self.model.lower()
        # Common vision-capable models
        vision_keywords = [
            "gpt-4",
            "gpt-4o",
            "gpt-4-vision",
            "claude",
            "gemini",
            "pixtral",
            "llava",
            "moondream",
            "qwen-vl",
            "vision",
        ]
        return any(k in m for k in vision_keywords)

    def supports_audio(self) -> bool:
        """Check if the configured model natively supports audio input."""
        m = self.model.lower()
        # Common audio-capable models (native, not just whisper)
        audio_keywords = ["gpt-4o", "gemini-1.5", "audio"]
        return any(k in m for k in audio_keywords)

    def supports_documents(self) -> bool:
        """Check if the configured model natively supports document (PDF) input."""
        m = self.model.lower()
        # Models known to support native PDF/doc parts (Claude 3.5, Gemini 1.5)
        doc_keywords = ["claude-3-5", "gemini-1.5", "gemini-3"]
        return any(k in m for k in doc_keywords)


def _default_model(provider: str) -> str:
    defaults = {
        "openai": "gpt-4o-mini",
        "openrouter": "openai/gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
        "compatible": "gpt-4o-mini",
    }
    return defaults.get(provider, "gpt-4o-mini")


_SUPPORTED_PROVIDERS = {"anthropic", "auto", "compatible", "openai", "openrouter"}
_RETRYABLE_STATUS_CODES = {408, 409, 429}


def _status_code(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        status_code = int(value)
    except (TypeError, ValueError):
        return None
    return status_code if 100 <= status_code <= 599 else None


def _structured_status_code(error: Exception) -> Optional[int]:
    status_code = _status_code(getattr(error, "status_code", None))
    if status_code is not None:
        return status_code

    response = getattr(error, "response", None)
    return _status_code(getattr(response, "status_code", None))


def _message_status_code(message: str) -> Optional[int]:
    at_start = re.match(r"^\s*([45]\d{2})\b", message)
    if at_start:
        return int(at_start.group(1))

    with_context = re.search(
        r"\b(?:http(?:\s+status)?|status(?:\s+code)?|error\s+code)\s*[:=]?\s*([45]\d{2})\b",
        message,
    )
    return int(with_context.group(1)) if with_context else None


def _is_retryable_error(error: Exception) -> bool:
    status_code = _structured_status_code(error)
    if status_code is not None:
        return status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code <= 599

    if isinstance(error, (ConnectionError, TimeoutError)):
        return True

    message = str(error).lower()
    status_code = _message_status_code(message)
    if status_code is not None:
        return status_code in _RETRYABLE_STATUS_CODES or 500 <= status_code <= 599

    retryable_patterns = (
        "rate limit",
        "too many requests",
        "timeout",
        "timed out",
        "connection error",
        "connection reset",
        "connection closed",
        "peer closed",
        "incomplete chunked read",
        "remote protocol error",
        "server disconnected",
        "network unreachable",
        "internal server error",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
    )
    return any(pattern in message for pattern in retryable_patterns)


def load_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(_SUPPORTED_PROVIDERS))
        raise ValueError(
            f"Unsupported LLM_PROVIDER {provider!r}. Expected one of: {supported}."
        )

    if provider == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("OPENROUTER_API_KEY"):
            provider = "openrouter"
        else:
            provider = "openai"

    model = os.getenv("MODEL_NAME")

    if provider == "openrouter":
        return LLMConfig(
            provider="openrouter",
            model=model
            or os.getenv("OPENROUTER_MODEL")
            or _default_model("openrouter"),
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        )

    if provider == "anthropic":
        return LLMConfig(
            provider="anthropic",
            model=model or os.getenv("ANTHROPIC_MODEL") or _default_model("anthropic"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            base_url=os.getenv("ANTHROPIC_BASE_URL"),
        )

    if provider == "compatible":
        return LLMConfig(
            provider="compatible",
            model=model or os.getenv("LLM_MODEL") or _default_model("compatible"),
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    return LLMConfig(
        provider="openai",
        model=model or os.getenv("OPENAI_MODEL") or _default_model("openai"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


class LLMRouter:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._openai_client: Optional[AsyncOpenAI] = None

        if self.config.provider in {"openai", "openrouter", "compatible"}:
            required_key = {
                "openai": "OPENAI_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
            }.get(self.config.provider)
            if required_key and not self.config.api_key:
                raise RuntimeError(
                    f"{required_key} is required for provider `{self.config.provider}`."
                )

            # Compatible providers/local proxies may intentionally be keyless.
            api_key = self.config.api_key or "not-required"
            self._openai_client = AsyncOpenAI(
                api_key=api_key,
                base_url=self.config.base_url,
                timeout=60.0,
            )

    async def chat_completions(
        self,
        *,
        messages: list,
        tools: list,
        tool_choice: str = "auto",
        stream: bool = False,
        thinking: bool = False,
    ) -> Any:
        max_attempts = 1 if stream else 3

        for attempt in range(max_attempts):
            try:
                return await self._chat_completions_inner(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    stream=stream,
                    thinking=thinking,
                )
            except Exception as error:
                if _is_retryable_error(error) and attempt < max_attempts - 1:
                    delay = 2.0 * (2**attempt) + random.uniform(0, 1)
                    print(
                        f"LLM API network or server error ({error}). Retrying in "
                        f"{delay:.2f}s (attempt {attempt + 2}/{max_attempts})..."
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

    async def _chat_completions_inner(
        self,
        *,
        messages: list,
        tools: list,
        tool_choice: str = "auto",
        stream: bool = False,
        thinking: bool = False,
    ) -> Any:
        await _get_rate_limiter().wait()

        if self.config.provider in {"openai", "openrouter", "compatible"}:
            if not self._openai_client:
                raise RuntimeError("OpenAI-compatible client is not initialized")

            kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
            }

            if thinking:
                model_lower = self.config.model.lower()
                if "o1" in model_lower or "o3" in model_lower:
                    kwargs["reasoning_effort"] = "high"

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            if stream:
                kwargs["stream"] = True
                if self.config.provider == "openai":
                    kwargs["stream_options"] = {"include_usage": True}

            extra_headers = {}
            if self.config.provider == "openrouter":
                referer = os.getenv("OPENROUTER_HTTP_REFERER")
                title = os.getenv("OPENROUTER_X_TITLE")
                if referer:
                    extra_headers["HTTP-Referer"] = referer
                if title:
                    extra_headers["X-Title"] = title
            if extra_headers:
                kwargs["extra_headers"] = extra_headers

            return await self._openai_client.chat.completions.create(**kwargs)

        if self.config.provider == "anthropic":
            if litellm_acompletion is None:
                raise RuntimeError(
                    "Anthropic provider requires `litellm`. Install dependencies with `pip install -r requirements.txt`."
                )
            if not self.config.api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is required for provider `anthropic`."
                )

            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "api_key": self.config.api_key,
                "timeout": 60,
            }
            if thinking and "claude-3-7" in self.config.model.lower():
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 4096}
                kwargs["max_tokens"] = 8192
            
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice
            if self.config.base_url:
                kwargs["api_base"] = self.config.base_url
                kwargs["base_url"] = self.config.base_url
            if stream:
                kwargs["stream"] = True

            return await litellm_acompletion(**kwargs)

        raise RuntimeError(f"Unsupported provider: {self.config.provider}")
