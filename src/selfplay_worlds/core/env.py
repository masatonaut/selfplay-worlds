"""The contract every game implements.

A ``GameEnv`` is the single source of truth: state, rules, legality, transitions
and the final result. It never calls a model and never decides who is asked first.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from selfplay_worlds.core.interaction import Interaction
from selfplay_worlds.core.types import Action, AgentOutput, GameResult, StepResult


class GameEnv(ABC):
    name: str = "base"

    # --- lifecycle -------------------------------------------------------------

    @abstractmethod
    def reset(self, *, seed: int | None = None) -> None:
        """Start a new game. The same seed must produce the same game."""

    @property
    @abstractmethod
    def player_ids(self) -> list[str]:
        """All players in seat order, including eliminated ones."""

    # --- what is happening now -------------------------------------------------

    @abstractmethod
    def current_interaction(self) -> Interaction | None:
        """The open decision point, or ``None`` once the game is over."""

    @abstractmethod
    def legal_actions(self, *, player_id: str) -> list[Action]:
        """Legal actions for this player in the current interaction.

        By convention the first element is the most conservative choice
        (for example "pass"). The Runner uses it as a fallback.
        """

    # --- information -----------------------------------------------------------

    @abstractmethod
    def observe(self, *, player_id: str) -> dict:
        """Everything this player is allowed to know, and nothing more.

        If the observation contains a ``"history"`` list, it must be public
        events only; the episode log stores it compactly.
        """

    def public_state(self) -> dict:
        """What every player and spectator can see."""
        return {}

    def public_history(self) -> list[str]:
        """All public events so far, in order."""
        return []

    @abstractmethod
    def full_state(self) -> dict:
        """God view, including hidden information. For logs and tests only."""

    # --- transitions -----------------------------------------------------------

    @abstractmethod
    def step(self, *, player_id: str, output: AgentOutput) -> StepResult:
        """Apply one player's output. Invalid outputs are rejected, never guessed."""

    @abstractmethod
    def result(self) -> GameResult | None:
        """The final result, or ``None`` while the game is still running."""

    # --- conveniences ----------------------------------------------------------

    def is_terminal(self) -> bool:
        return self.current_interaction() is None

    def player_name(self, player_id: str) -> str:
        return player_id

    def config(self) -> dict[str, Any]:
        return {}


@dataclass(frozen=True)
class GameSpec:
    """Everything the rest of the framework needs to know about one game."""

    name: str
    make_env: Callable[..., GameEnv]
    rules_text: str = ""
    """Plain-language rules, used by the LLM agent's system prompt."""
    render_observation: Callable[..., str] | None = None
    """Turns an observation into prompt text for LLM agents."""
    scripted_policy: Callable[..., AgentOutput] | None = None
    """Default rule-based policy for deterministic agents."""
