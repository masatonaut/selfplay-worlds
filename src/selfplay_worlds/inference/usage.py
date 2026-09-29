"""Explicit per-episode inference usage and simple hard budgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UsageLimitExceeded(RuntimeError):
    pass


@dataclass
class UsageLimits:
    max_calls: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "max_calls": self.max_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass
class UsageTracker:
    limits: UsageLimits | None = None
    model_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_latency_s: float = 0.0
    cost_usd: float | None = None

    def reset(self) -> None:
        """Start a fresh episode while preserving configured limits."""
        self.model_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_latency_s = 0.0
        self.cost_usd = None

    def check_before_call(self) -> None:
        if self.limits is None:
            return
        checks = (
            (self.limits.max_calls, self.model_calls, "model calls"),
            (self.limits.max_input_tokens, self.total_input_tokens, "input tokens"),
            (self.limits.max_output_tokens, self.total_output_tokens, "output tokens"),
        )
        for limit, used, label in checks:
            if limit is not None and used >= limit:
                raise UsageLimitExceeded(f"inference budget exhausted: {used}/{limit} {label}")

    def record(self, metadata: dict[str, Any]) -> None:
        if not metadata.get("model"):
            return
        self.model_calls += 1
        self.total_input_tokens += metadata.get("input_tokens") or 0
        self.total_output_tokens += metadata.get("output_tokens") or 0
        self.total_latency_s += metadata.get("latency_s") or 0.0
        reported_cost = metadata.get("cost_usd")
        if reported_cost is not None:
            self.cost_usd = (self.cost_usd or 0.0) + float(reported_cost)

    def state_dict(self) -> dict[str, Any]:
        return {
            "limits": self.limits.to_dict() if self.limits else None,
            "model_calls": self.model_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_latency_s": round(self.total_latency_s, 6),
            "cost_usd": self.cost_usd,
        }

    def load_state_dict(self, data: dict[str, Any]) -> None:
        limits = data.get("limits")
        self.limits = UsageLimits(**limits) if limits else None
        self.model_calls = data.get("model_calls", 0)
        self.total_input_tokens = data.get("total_input_tokens", 0)
        self.total_output_tokens = data.get("total_output_tokens", 0)
        self.total_latency_s = data.get("total_latency_s", 0.0)
        self.cost_usd = data.get("cost_usd")
