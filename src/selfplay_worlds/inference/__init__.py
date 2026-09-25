"""Optional model inference. The deterministic framework never imports this package."""

from selfplay_worlds.inference.base import Generation, InferenceBackend, MockBackend
from selfplay_worlds.inference.openai_compatible import (
    OpenAICompatibleBackend,
    OpenRouterBackend,
    VLLMBackend,
)

__all__ = [
    "Generation",
    "InferenceBackend",
    "MockBackend",
    "OpenAICompatibleBackend",
    "OpenRouterBackend",
    "VLLMBackend",
]
