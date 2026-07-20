"""Groq — Ultra-fast inference. Free tier available."""

import time
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class GroqProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "llama-3.1-8b-instant", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        from groq import Groq

        key = api_key or config.GROQ_API_KEY
        if not key:
            raise ValueError("No Groq API key configured")

        client = Groq(api_key=key)
        start = time.time()

        response = client.chat.completions.create(
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
            provider="groq",
        )

    def is_available(self) -> bool:
        return bool(config.GROQ_API_KEY)

    def get_supported_models(self) -> list:
        return ["llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]