from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

try:
    from litellm import acompletion as litellm_acompletion
except Exception:
    litellm_acompletion = None

import time
import asyncio
import random
import threading

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
            sys.stdout.write(f"\n[Rate Limit] Reached limit of {self.rpm_limit} requests/min. Pausing for {sleep_time:.1f}s to prevent exhaustion...\n")
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
            "gpt-4", "gpt-4o", "gpt-4-vision", "claude", "gemini", "pixtral", 
            "llava", "moondream", "qwen-vl", "vision"
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


def load_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()

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
            api_key=os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"),
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
            api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
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
            # Some compatible providers/local proxies do not require a key.
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
    ) -> Any:
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                return await self._chat_completions_inner(
                    messages=messages, tools=tools, tool_choice=tool_choice, stream=stream
                )
            except Exception as e:
                err_msg = str(e).lower()
                retryable_patterns = [
                    "429", "rate limit", "500", "502", "503", "504", "timeout", 
                    "too many requests", "peer closed", "incomplete chunked read", 
                    "connection reset", "remote protocol error", "connection closed"
                ]
                is_retryable = any(x in err_msg for x in retryable_patterns)
                if is_retryable and attempt < max_retries - 1:
                    delay = 2.0 * (2 ** attempt) + random.uniform(0, 1)
                    print(f"LLM API network or server error ({e}). Retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries})...")
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
    ) -> Any:
        await _get_rate_limiter().wait()
        
        if self.config.provider in {"openai", "openrouter", "compatible"}:
            if not self._openai_client:
                raise RuntimeError("OpenAI-compatible client is not initialized")

            kwargs: Dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
            }

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
