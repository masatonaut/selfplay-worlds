"""Small, replaceable policies for deciding who is queried next."""

from __future__ import annotations

from abc import ABC, abstractmethod

from selfplay_worlds.core.interaction import Interaction


class Scheduler(ABC):
    """Orders the actors eligible for one interaction."""

    @abstractmethod
    def order(self, *, interaction: Interaction) -> list[str]:
        """Return the query order for this interaction."""

    def describe(self) -> str:
        return type(self).__name__


class RoundRobinScheduler(Scheduler):
    """Deterministic seat order, repeated by Runner for discussion rounds."""

    def order(self, *, interaction: Interaction) -> list[str]:
        return list(interaction.eligible_players)
