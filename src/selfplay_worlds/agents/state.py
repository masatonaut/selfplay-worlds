"""Serializable memory owned by one agent, never private reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    observations: list[dict[str, Any]] = field(default_factory=list)
    produced_messages: list[str] = field(default_factory=list)
    attempted_actions: list[dict[str, Any] | None] = field(default_factory=list)
    accepted_actions: list[dict[str, Any]] = field(default_factory=list)
    validation_feedback: list[str | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": list(self.observations),
            "produced_messages": list(self.produced_messages),
            "attempted_actions": list(self.attempted_actions),
            "accepted_actions": list(self.accepted_actions),
            "validation_feedback": list(self.validation_feedback),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentState:
        return cls(
            observations=list(data.get("observations", [])),
            produced_messages=list(data.get("produced_messages", [])),
            attempted_actions=list(data.get("attempted_actions", [])),
            accepted_actions=list(data.get("accepted_actions", [])),
            validation_feedback=list(data.get("validation_feedback", [])),
        )
