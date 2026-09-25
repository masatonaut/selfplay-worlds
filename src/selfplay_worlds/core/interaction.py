"""The concept that makes the framework game-agnostic.

An ``Interaction`` describes the current decision point: which rule is being
applied (``phase``), how agents should be scheduled (``mode``), and who is
allowed to act (``eligible_players``).

Division of labour:
    Environment -> WHO MAY act, and WHAT is legal.
    Runner      -> WHO IS ASKED FIRST.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InteractionMode(StrEnum):
    """How the Runner should schedule agents. The same four modes for every game."""

    SINGLE = "single"
    """Exactly one player must act."""

    RESPONSE_WINDOW = "response_window"
    """Eligible players may respond or pass. The environment may close it early."""

    DISCUSSION = "discussion"
    """Players exchange messages until the environment closes the discussion."""

    SIMULTANEOUS = "simultaneous"
    """Every eligible player acts without seeing the others; resolved together."""


class MessagePolicy(StrEnum):
    """Whether free-text messages are accepted in this interaction."""

    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass(frozen=True)
class Interaction:
    """What is happening right now in the game."""

    interaction_id: int
    """Increases every time a new interaction opens. The Runner uses it to notice
    that the environment closed a window (for example because someone challenged)."""

    phase: str
    """Game-specific rule state, for example ``"challenge_action"``."""

    mode: InteractionMode
    """Framework-level scheduling pattern."""

    eligible_players: tuple[str, ...]
    """Who may act now, in the environment's default order."""

    message_policy: MessagePolicy = MessagePolicy.OPTIONAL
    description: str = ""
    """One human-readable line, used in prompts and traces."""

    def to_dict(self) -> dict:
        return {
            "id": self.interaction_id,
            "phase": self.phase,
            "mode": self.mode.value,
            "eligible_players": list(self.eligible_players),
            "message_policy": self.message_policy.value,
            "description": self.description,
        }
