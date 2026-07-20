"""Abstract LLM interface. Every provider implements this."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMMessage:
    role: str       # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    provider: str = ""


class BaseLLMProvider(ABC):

    @abstractmethod
    def generate(self, messages: list, model: str, temperature: float = 0.7, max_tokens: int = 1024, api_key: str = "") -> LLMResponse:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    def get_supported_models(self) -> list:
        return []