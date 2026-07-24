"""Ollama — Free local LLM. No API key needed."""

import time
import requests
from .base import BaseLLMProvider, LLMMessage, LLMResponse
from ..config import config


class OllamaProvider(BaseLLMProvider):

    def __init__(self):
        self.base_url = config.OLLAMA_BASE_URL.rstrip("/")

    def generate(self, messages: list, model: str = "", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        model = model or config.DEFAULT_LLM_MODEL
        start = time.time()

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=200,
        )
        response.raise_for_status()
        data = response.json()

        latency = int((time.time() - start) * 1000)

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=data.get("model", model),
            tokens_input=data.get("prompt_eval_count", 0),
            tokens_output=data.get("eval_count", 0),
            latency_ms=latency,
            provider="ollama",
        )

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_local_models(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def get_supported_models(self) -> list:
        return self.list_local_models()