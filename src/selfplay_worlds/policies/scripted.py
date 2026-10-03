"""Deterministic policies: no model, and the same seed gives the same behaviour."""

from __future__ import annotations

import random
from abc import abstractmethod
from typing import Any

from selfplay_worlds.policies.base import Policy


class ScriptedPolicy(Policy):
    """Rule-based play. The RNG lives on the instance, so saving the policy saves it."""

    def __init__(self, *, game_name: str, seed: int = 0) -> None:
        super().__init__(game_name=game_name)
        self.rng = random.Random(seed)

    def get_action(self, *, observation: dict[str, Any], conversation: list[dict[str, Any]]) -> dict[str, Any]:
        return self.step(observation=observation, conversation=conversation)

    @abstractmethod
    def step(self, *, observation: dict[str, Any], conversation: list[dict[str, Any]]) -> dict[str, Any]:
        """Return an answer for this observation."""


class FirstOptionPolicy(ScriptedPolicy):
    """Always the first option, which games list as the most conservative choice."""

    def step(self, *, observation, conversation):
        return {"option": 1}


class RandomPolicy(ScriptedPolicy):
    """A uniformly random option. Useful for stress tests, not for demos."""

    def step(self, *, observation, conversation):
        return {"option": self.rng.randint(1, len(observation["options"]))}


class ReplayPolicy(ScriptedPolicy):
    """Plays fixed answers and messages first, then falls back to another policy.

    Useful for tests and demos ("Alice claims Duke, Carol challenges").
    """

    def __init__(
        self,
        *,
        game_name: str,
        answers: list[dict[str, Any]] | None = None,
        messages: list[str | None] | None = None,
        then: Policy | None = None,
    ) -> None:
        super().__init__(game_name=game_name)
        self.answers = list(answers or [])
        self.messages = list(messages or [])
        self.then = then or FirstOptionPolicy(game_name=game_name)

    def get_message(self, *, observation, conversation):
        if self.messages:
            return self.messages.pop(0)
        return self.then.get_message(observation=observation, conversation=conversation)

    def step(self, *, observation, conversation):
        if self.answers:
            return self.answers.pop(0)
        return self.then.get_action(observation=observation, conversation=conversation)
