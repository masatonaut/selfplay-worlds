"""Small, replaceable policies for deciding who is asked first."""

from __future__ import annotations

from abc import ABC, abstractmethod

from selfplay_worlds.core.env import DialoguePhase


class Scheduler(ABC):
    """Orders the players eligible in one dialogue phase."""

    @abstractmethod
    def order(self, *, phase: DialoguePhase) -> list[str]:
        """Return the order in which players are asked in this phase."""

    def describe(self) -> str:
        return type(self).__name__


class RoundRobinScheduler(Scheduler):
    """The environment's default order."""

    def order(self, *, phase: DialoguePhase) -> list[str]:
        return list(phase.eligible)
