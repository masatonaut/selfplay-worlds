"""Where model text comes from. Everything else only calls ``generate``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationConfig:
    max_tokens: int = 300
    temperature: float = 0.7
    top_p: float | None = None
    top_k: int | None = None
    json_schema: dict[str, Any] | None = None
    reasoning: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "structured_output": self.json_schema is not None,
            "reasoning": self.reasoning,
        }


GEMMA_4_GENERATION_CONFIG = GenerationConfig(temperature=1.0, top_p=0.95, top_k=64, reasoning=False)


@dataclass
class Generation:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_s: float | None = None
    cost_usd: float | None = None


class InferenceBackend:
    """Turns chat messages into text. Implementations never see game objects."""

    name: str = "base"
    model: str = ""

    def generate(
        self,
        *,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float | None = None,
        top_k: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> Generation:
        raise NotImplementedError


class MockBackend(InferenceBackend):
    """No model at all: canned replies, then an optional reply function.

    Used by the tests and by the offline demo. It records every request in
    ``calls`` so tests can check exactly what a model would have been shown.
    """

    name = "mock"

    def __init__(
        self,
        *,
        replies: list[str] | None = None,
        respond: Callable[[list[dict]], str] | None = None,
        model: str = "mock",
    ) -> None:
        self.model = model
        self._replies = list(replies or [])
        self._respond = respond
        self.calls: list[list[dict]] = []

    def generate(
        self,
        *,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float | None = None,
        top_k: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> Generation:
        self.calls.append(messages)
        if self._replies:
            text = self._replies.pop(0)
        elif self._respond is not None:
            text = self._respond(messages)
        else:
            raise RuntimeError("MockBackend has no replies left")
        return Generation(text=text, model=self.model, latency_s=0.0)
