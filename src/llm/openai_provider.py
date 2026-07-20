"""OpenAI — GPT-4o, GPT-4o-mini."""

import time
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class OpenAIProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "gpt-4o-mini", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        from openai import OpenAI

        key = api_key or config.OPENAI_API_KEY
        if not key:
            raise ValueError("No OpenAI API key configured")

        client = OpenAI(api_key=key)
        start = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        latency = int((time.time() - start) * 1000)
        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_input=usage.prompt_tokens if usage else 0,
            tokens_output=usage.completion_tokens if usage else 0,
            latency_ms=latency,
            provider="openai",
        )

    def is_available(self) -> bool:
        return bool(config.OPENAI_API_KEY)

    def get_supported_models(self) -> list:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]