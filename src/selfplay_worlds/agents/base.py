"""Agents turn a player-specific observation into an AgentOutput."""

from __future__ import annotations

from abc import ABC, abstractmethod

from selfplay_worlds.core.interaction import Interaction
from selfplay_worlds.core.types import Action, AgentOutput


class Agent(ABC):
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
