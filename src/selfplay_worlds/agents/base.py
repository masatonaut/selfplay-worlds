"""Agents turn a player-specific observation into an AgentOutput."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from selfplay_worlds.agents.state import AgentState
from selfplay_worlds.core.interaction import Interaction
from selfplay_worlds.core.types import Action, AgentOutput, action_to_dict


class Agent(ABC):
    def __init__(self) -> None:
        self.state = AgentState()

    @abstractmethod
    def act(
        self,
        *,
        observation: dict,
        interaction: Interaction,
        legal_actions: list[Action],
        feedback: str | None = None,
    ) -> AgentOutput:
        """Choose a message and/or an action.

        ``feedback`` is set when the previous attempt was rejected, and holds
        the environment's error message.
        """

    def describe(self) -> dict:
        """How this agent is recorded in the episode log."""
        return {"type": type(self).__name__, "model": None, "backend": None}

    def record_attempt(
        self,
        *,
        observation: dict[str, Any],
        output: AgentOutput,
        accepted: bool,
        feedback: str | None,
    ) -> None:
        """Remember only what this agent observed, said, tried, and was told."""
        self.state.observations.append(observation)
        if output.message:
            self.state.produced_messages.append(output.message)
        action = action_to_dict(output.action)
        self.state.attempted_actions.append(action)
        if accepted and action is not None:
            self.state.accepted_actions.append(action)
        self.state.validation_feedback.append(feedback)

    def state_dict(self) -> dict[str, Any]:
        return self.state.to_dict()

    def load_state_dict(self, data: dict[str, Any]) -> None:
        self.state = AgentState.from_dict(data)
