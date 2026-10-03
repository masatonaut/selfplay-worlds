"""The contract every game implements.

A ``GameEnv`` is the single source of truth: settings, state, rules, legality,
transitions, done and rewards. It never sees talk, prompts, models or policies,
and it never decides who is asked first.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from selfplay_worlds.core.persist import load_pickle, save_pickle


class Action(ABC):
    """One game-specific action.

    Policies never build these. They return a plain answer dict, for example
    ``{"option": 3}``, and ConversationGame turns it into the game's Action with
    ``from_answer`` before calling ``GameEnv.step``.
    """

    @classmethod
    @abstractmethod
    def from_answer(cls, *, answer: dict, player_id: str, observation: dict) -> Action:
        """Turn a policy's answer into this game's Action.

        Raise ``ValueError(reason)`` if the answer cannot be read (for example
        option 9 of 4). Reading an answer is not checking legality: ``step`` does that.
        """

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable form, used in the conversation record."""


class DialogueMode(StrEnum):
    """How ConversationGame schedules a phase. The same four modes for every game."""

    ACTION = "action"
    """One player acts, optionally talking first."""

    RESPONSE_WINDOW = "response_window"
    """Eligible players respond in order. The environment may close it early."""

    DISCUSSION = "discussion"
    """Talk rounds for everyone, then each eligible player acts."""

    SIMULTANEOUS = "simultaneous"
    """Every eligible player answers before anyone's action is applied."""


@dataclass(frozen=True)
class DialoguePhase:
    """What is happening right now in the game."""

    phase_id: int
    """Increases every time the environment opens a new phase. ConversationGame
    uses it to notice that the environment closed a window early."""

    phase: str
    """Game-specific rule state, for example ``"challenge_action"``."""

    mode: DialogueMode
    eligible: tuple[str, ...]
    """Who may act now, in the environment's default order."""

    talk_rounds: int = 0
    """How many times each speaker may talk before acting. 0 means straight to the action."""

    description: str = ""
    """One human-readable line, used in prompts and traces."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "phase": self.phase,
            "mode": self.mode.value,
            "eligible": list(self.eligible),
            "talk_rounds": self.talk_rounds,
            "description": self.description,
        }


@dataclass
class StepResult:
    """The environment's answer to one ``step`` call."""

    accepted: bool
    error: str | None = None
    """Why the action was rejected. A rejected action changes nothing."""

    public_events: list[str] = field(default_factory=list)
    """Human-readable descriptions of everything that became public in this step."""


class GameEnv(ABC):
    action_class: ClassVar[type[Action]]
    """The game's Action subclass. ConversationGame calls its ``from_answer``."""

    def __init__(self, *, name: str, game_config: dict[str, Any]) -> None:
        self.name = name
        self.game_config = dict(game_config)
        """Every game setting, the seed included. Subclasses read settings only from here."""
        self.reset()

    def reset(self) -> None:
        """Start the game from ``game_config``. The same config must produce the same game.

        Subclasses call ``super().reset()`` and then build their state ONLY from
        ``self.game_config``: their own attributes do not exist yet when the base
        ``__init__`` first calls this.
        """
        self.n_steps = 0

    # --- what is happening now -------------------------------------------------

    @property
    @abstractmethod
    def player_ids(self) -> list[str]:
        """All players in seat order, including eliminated ones."""

    @abstractmethod
    def get_dialogue_phase(self) -> DialoguePhase | None:
        """The open phase, or ``None`` once the game is over."""

    @abstractmethod
    def get_observation(self, *, player_id: str) -> dict[str, Any]:
        """Everything this player may know, and nothing more. It includes:

        * ``"history"``: the game's public history.
        * ``"options"``: the menu this player can pick from by number right now
          (a menu for prompts and policies, not a legality guarantee).
        """

    @abstractmethod
    def get_state(self, **kwargs: Any) -> dict[str, Any]:
        """Game state as a dict. ``kwargs`` select the view (for example ``view="full"``).

        The returned dict MUST include:
            "done":    bool
            "rewards": dict[player_id, float]   (zeros until the game ends)
        """

    def player_name(self, player_id: str) -> str:
        return player_id

    # --- transitions -----------------------------------------------------------

    def step(self, *, player_id: str, action: Action) -> StepResult:
        """Apply one action. ``n_steps`` counts accepted actions only."""
        result = self._step(player_id=player_id, action=action)
        if result.accepted:
            self.n_steps += 1
        return result

    @abstractmethod
    def _step(self, *, player_id: str, action: Action) -> StepResult:
        """Apply one action. Legality is checked HERE, by each game.

        If the action is not legal, change nothing and return
        ``StepResult(accepted=False, error=<why>)``.
        """

    # --- saving ------------------------------------------------------------------

    def save(self, *, path: str | Path) -> Path:
        """Pickle the whole environment, RNG included."""
        return save_pickle(path=path, value=self)

    def load(self, *, path: str | Path) -> None:
        """Adopt the state saved at ``path``.

        Raises ``ValueError`` naming every key whose value differs between the
        saved ``game_config`` and this environment's, or that only one of them has.
        """
        saved = load_pickle(path=path)
        if type(saved) is not type(self):
            raise TypeError(f"{path} holds a {type(saved).__name__}, not a {type(self).__name__}")
        mismatched = config_mismatches(saved=saved.game_config, current=self.game_config)
        if mismatched:
            raise ValueError(f"saved game_config does not match this environment's: {mismatched}")
        self.__dict__.clear()
        self.__dict__.update(saved.__dict__)


def config_mismatches(*, saved: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Keys that are missing from one side or have different values, sorted."""
    keys = set(saved) | set(current)
    return sorted(key for key in keys if key not in saved or key not in current or saved[key] != current[key])
