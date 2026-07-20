"""Anthropic — Claude Sonnet, Haiku, Opus."""

import time
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class AnthropicProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "claude-sonnet-4-20250514", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        from anthropic import Anthropic

        key = api_key or config.ANTHROPIC_API_KEY
        if not key:
            raise ValueError("No Anthropic API key configured")

        client = Anthropic(api_key=key)

        system = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        start = time.time()
        response = client.messages.create(
            model=model,
            system=system.strip() or "You are a helpful assistant.",
            messages=chat_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latency = int((time.time() - start) * 1000)

        return LLMResponse(
            content=response.content[0].text if response.content else "",
            model=response.model,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
            latency_ms=latency,
            provider="anthropic",
        )

    def is_available(self) -> bool:
        return bool(config.ANTHROPIC_API_KEY)

    def get_supported_models(self) -> list:
        return ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"]