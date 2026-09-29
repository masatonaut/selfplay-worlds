"""Small data types exchanged between the environment, agents and the Runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Action(Protocol):
    """A game-owned, JSON-serializable action."""

    def to_dict(self) -> dict[str, Any]: ...


def action_to_dict(action: Action | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if action is None:
        return None
    if isinstance(action, Action):
        return action.to_dict()
    if isinstance(action, Mapping):
        return dict(action)
    return None


@dataclass
class AgentOutput:
    """What an agent returns. Language and structured action are kept separate.

    An agent may return an action only, a message only, or both.
    """

    action: Action | Mapping[str, Any] | None = None
    message: str | None = None
    raw_model_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "action": action_to_dict(self.action),
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


@dataclass(frozen=True)
class DecisionEvent:
    """One submitted decision attempt, accepted or rejected."""

    interaction: dict[str, Any]
    actor: str
    observation: dict[str, Any]
    output: AgentOutput
    attempt: int
    accepted: bool
    error: str | None
    public_events: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "step",
            "interaction": self.interaction,
            "actor": self.actor,
            "player_observation": self.observation,
            "output": self.output.to_dict(),
            "auto": bool(self.output.metadata.get("auto")),
            "fallback": bool(self.output.metadata.get("fallback")),
            "attempt": self.attempt,
            "accepted": self.accepted,
            "error": self.error,
            "public_events": list(self.public_events),
        }
