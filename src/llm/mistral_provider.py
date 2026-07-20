"""Mistral AI."""

import time
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class MistralProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "mistral-small-latest", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        from mistralai import Mistral

        key = api_key or config.MISTRAL_API_KEY
        if not key:
            raise ValueError("No Mistral API key configured")

        client = Mistral(api_key=key)
        start = time.time()

        response = client.chat.complete(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        latency = int((time.time() - start) * 1000)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_input=response.usage.prompt_tokens if response.usage else 0,
            tokens_output=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency,
            provider="mistral",
        )

    def is_available(self) -> bool:
        return bool(config.MISTRAL_API_KEY)

    def get_supported_models(self) -> list:
        return ["mistral-large-latest", "mistral-small-latest"]