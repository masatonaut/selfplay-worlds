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
        super().__init__()
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

    def state_dict(self) -> dict:
        data = super().state_dict()
        data["implementation"] = {
            "rng_state": self._rng.getstate(),
            "remaining_script": [output.to_dict() for output in self._script],
        }
        return data

    def load_state_dict(self, data: dict) -> None:
        super().load_state_dict(data)
        implementation = data.get("implementation", {})
        if "rng_state" in implementation:
            self._rng.setstate(_tuples(implementation["rng_state"]))
        if "remaining_script" in implementation:
            self._script = [AgentOutput(**output) for output in implementation["remaining_script"]]


class RandomAgent(Agent):
    """Uniformly random legal action. Useful for stress tests, not for demos."""

    def __init__(self, *, seed: int = 0) -> None:
        super().__init__()
        self._rng = random.Random(seed)

    def act(self, *, observation, interaction: Interaction, legal_actions: list[Action], feedback=None) -> AgentOutput:
        message = "(random)" if interaction.message_policy is MessagePolicy.REQUIRED else None
        return AgentOutput(action=self._rng.choice(legal_actions), message=message)

    def state_dict(self) -> dict:
        data = super().state_dict()
        data["implementation"] = {"rng_state": self._rng.getstate()}
        return data

    def load_state_dict(self, data: dict) -> None:
        super().load_state_dict(data)
        implementation = data.get("implementation", {})
        if "rng_state" in implementation:
            self._rng.setstate(_tuples(implementation["rng_state"]))


def _tuples(value):
    if isinstance(value, list):
        return tuple(_tuples(item) for item in value)
    return value
