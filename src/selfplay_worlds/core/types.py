"""Small data types exchanged between the environment, agents and the Runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Action = dict[str, Any]
"""A structured game action with a ``"type"`` key, for example ``{"type": "tax"}``
or ``{"type": "steal", "target": "p1"}``. Only the environment decides legality."""


@dataclass
class AgentOutput:
    """What an agent returns. Language and structured action are kept separate.

    An agent may return an action only, a message only, or both.
    """

    action: Action | None = None
    message: str | None = None
    raw_model_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "action": self.action,
            "raw_model_output": self.raw_model_output,
            "metadata": self.metadata,
        }


@dataclass
class StepResult:
    """The environment's answer to one ``step`` call."""

    accepted: bool
    error: str | None = None
    public_events: list[str] = field(default_factory=list)
    """Human-readable descriptions of everything that became public in this step."""


@dataclass
class GameResult:
    winners: list[str]
    payoffs: dict[str, float]
    termination_reason: str

    def to_dict(self) -> dict:
        return {
            "winners": list(self.winners),
            "payoffs": dict(self.payoffs),
            "termination_reason": self.termination_reason,
        }
