"""LLM Router — picks the right provider. This is the ONLY thing the rest of the code talks to."""

from .base import LLMMessage, LLMResponse
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .anthropic_provider import AnthropicProvider
from .groq_provider import GroqProvider
from .mistral_provider import MistralProvider
from ..config import config


class LLMRouter:

    def __init__(self):
        self.providers = {
            "ollama": OllamaProvider(),
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "anthropic": AnthropicProvider(),
            "groq": GroqProvider(),
            "mistral": MistralProvider(),
        }

    def generate(self, messages: list, provider: str = "", model: str = "", temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        provider = provider or config.DEFAULT_LLM_PROVIDER
        model = model or config.DEFAULT_LLM_MODEL

        llm = self.providers.get(provider)
        if not llm:
            raise ValueError(f"Unknown provider: {provider}")

        return llm.generate(messages, model, temperature, max_tokens, api_key)

    def list_available(self) -> dict:
        return {name: p.is_available() for name, p in self.providers.items()}

    def list_all_models(self) -> dict:
        return {name: p.get_supported_models() for name, p in self.providers.items()}


# Single instance used everywhere
llm_router = LLMRouter()