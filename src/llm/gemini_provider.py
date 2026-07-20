"""Google Gemini — Free tier available."""

import time
from .base import BaseLLMProvider, LLMResponse
from ..config import config


class GeminiProvider(BaseLLMProvider):

    def generate(self, messages: list, model: str = "gemini-2.0-flash", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        import google.generativeai as genai

        key = api_key or config.GOOGLE_AI_API_KEY
        if not key:
            raise ValueError("No Google AI API key configured")

        genai.configure(api_key=key)

        system = ""
        contents = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [m.content]})

        gen_model = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

        if system:
            gen_model._system_instruction = system

        start = time.time()
        response = gen_model.generate_content(contents)
        latency = int((time.time() - start) * 1000)

        return LLMResponse(
            content=response.text or "",
            model=model,
            latency_ms=latency,
            provider="gemini",
        )

    def is_available(self) -> bool:
        return bool(config.GOOGLE_AI_API_KEY)

    def get_supported_models(self) -> list:
        return ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"]