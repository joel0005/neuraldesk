"""Google Gemini — Free tier available."""

import time
import requests
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class GeminiProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "gemini-2.0-flash", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        key = api_key or config.GOOGLE_AI_API_KEY
        if not key:
            raise ValueError("No Google AI API key configured")

        # Build contents from messages
        system_text = ""
        contents = []
        for m in messages:
            if m.role == "system":
                system_text = m.content
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        # Use REST API directly — avoids SDK version issues
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}

        start = time.time()
        response = requests.post(url, json=body, timeout=120)
        response.raise_for_status()
        data = response.json()
        latency = int((time.time() - start) * 1000)

        # Extract text from response
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            text = "No response generated."

        return LLMResponse(
            content=text,
            model=model,
            latency_ms=latency,
            provider="gemini",
        )

    def is_available(self) -> bool:
        return bool(config.GOOGLE_AI_API_KEY)

    def get_supported_models(self) -> list:
        return ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"]