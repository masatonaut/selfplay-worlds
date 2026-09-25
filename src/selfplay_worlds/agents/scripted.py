"""Deterministic agents: no model, same seed gives the same behaviour."""

from __future__ import annotations

import random
from collections.abc import Callable

from selfplay_worlds.agents.base import Agent
from selfplay_worlds.core.interaction import Interaction, MessagePolicy
from selfplay_worlds.core.types import Action, AgentOutput

Policy = Callable[..., AgentOutput]
"""policy(observation=..., interaction=..., legal_actions=..., rng=...) -> AgentOutput"""


def first_legal_policy(*, observation, interaction, legal_actions, rng) -> AgentOutput:
    """The most conservative choice: the environment lists it first."""
    message = "(pass)" if interaction.message_policy is MessagePolicy.REQUIRED else None
    return AgentOutput(action=legal_actions[0], message=message)


class ScriptedAgent(Agent):
    """Plays a fixed script first, then follows a rule-based policy.

    The script is useful for tests and demos ("Alice claims Duke, Carol
    challenges"). The policy keeps the game going after the script runs out.
    """

    def __init__(
        self,
        *,
        policy: Policy | None = None,
        script: list[AgentOutput] | None = None,
        seed: int = 0,
        label: str | None = None,
    ) -> None:
        self._policy = policy or first_legal_policy
        self._script = list(script or [])
        self._rng = random.Random(seed)
        self._label = label or getattr(self._policy, "__name__", "policy")

    def act(self, *, observation, interaction: Interaction, legal_actions: list[Action], feedback=None) -> AgentOutput:
        if self._script:
            return self._script.pop(0)
        return self._policy(
            observation=observation, interaction=interaction, legal_actions=legal_actions, rng=self._rng
        )

    def describe(self) -> dict:
        return {"type": "ScriptedAgent", "policy": self._label, "model": None, "backend": None}


class RandomAgent(Agent):
    """Uniformly random legal action. Useful for stress tests, not for demos."""

    def __init__(self, *, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def act(self, *, observation, interaction: Interaction, legal_actions: list[Action], feedback=None) -> AgentOutput:
        message = "(random)" if interaction.message_policy is MessagePolicy.REQUIRED else None
        return AgentOutput(action=self._rng.choice(legal_actions), message=message)
