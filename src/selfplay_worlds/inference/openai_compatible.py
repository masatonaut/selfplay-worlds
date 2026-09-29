"""Backends for servers that speak the OpenAI chat-completions API.

OpenRouter (hosted models) and vLLM (a server you start yourself, for example
on a CARC GPU node) both speak this API, so one small class covers both.

Requires the optional extra:  uv sync --extra llm
Credentials come only from environment variables, never from files in this
repository:

    OPENROUTER_API_KEY   required for OpenRouterBackend
    VLLM_BASE_URL        optional, default http://localhost:8000/v1
    VLLM_API_KEY         optional, only if your vLLM server was started with --api-key
"""

from __future__ import annotations

import os
import time
from typing import Any

from selfplay_worlds.inference.base import Generation, InferenceBackend


class OpenAICompatibleBackend(InferenceBackend):
    name = "openai-compatible"

    def __init__(self, *, model: str, base_url: str, api_key: str, timeout: float = 120.0) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise ImportError("LLM backends need the optional 'openai' package: uv sync --extra llm") from error
        self.model = model
        self.base_url = base_url
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

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
        start = time.perf_counter()
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            request["top_p"] = top_p
        if top_k is not None:
            request["extra_body"] = {"top_k": top_k}
        if json_schema is not None:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "agent_output", "schema": json_schema},
            }
        response = self._client.chat.completions.create(**request)
        usage = response.usage
        return Generation(
            text=response.choices[0].message.content or "",
            model=response.model or self.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            latency_s=round(time.perf_counter() - start, 3),
        )


class OpenRouterBackend(OpenAICompatibleBackend):
    """Hosted models through OpenRouter. Costs money per call."""

    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, *, model: str, api_key: str | None = None, timeout: float = 120.0) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Export it in your shell; never write it into a file in this repository."
            )
        super().__init__(model=model, base_url=self.BASE_URL, api_key=key, timeout=timeout)


class VLLMBackend(OpenAICompatibleBackend):
    """A vLLM OpenAI-compatible server that is already running. This class never starts one."""

    name = "vllm"

    def __init__(
        self, *, model: str, base_url: str | None = None, api_key: str | None = None, timeout: float = 120.0
    ) -> None:
        url = base_url or os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
        key = api_key or os.environ.get("VLLM_API_KEY", "EMPTY")  # vLLM ignores the key unless started with --api-key
        super().__init__(model=model, base_url=url, api_key=key, timeout=timeout)
