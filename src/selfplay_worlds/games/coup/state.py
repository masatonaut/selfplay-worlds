"""The source of truth for one Coup game. Saved by pickling the environment."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from selfplay_worlds.games.coup.actions import CoupActionType
from selfplay_worlds.games.coup.cards import Card


class CoupPhase(StrEnum):
    ACTION = "action"
    CHALLENGE_ACTION = "challenge_action"
    BLOCK_ACTION = "block_action"
    CHALLENGE_BLOCK = "challenge_block"
    LOSE_INFLUENCE = "lose_influence"
    EXCHANGE = "exchange"


class CoupContinuation(StrEnum):
    """What the turn does once every queued influence loss is resolved."""

    ACTION_CLAIM_SURVIVES = "action_claim_survives"
    BLOCK_STANDS = "block_stands"
    RESOLVE_ACTION = "resolve_action"
    END_TURN = "end_turn"


@dataclass
class CoupPlayerState:
    id: str
    name: str
    coins: int
    hidden: list[Card]
    revealed: list[Card] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return bool(self.hidden)


@dataclass
class CoupTurnState:
    actor: str
    action: CoupActionType | None = None
    target: str | None = None
    paid: int = 0
    blocker: str | None = None
    block_claim: Card | None = None


@dataclass
class CoupState:
    players: list[CoupPlayerState]
    deck: list[Card]
    rng: random.Random
    """The only source of randomness after setup. Saved with the state."""
    start_player: str
    current_turn: CoupTurnState | None = None
    phase: CoupPhase | None = None
    eligible_players: list[str] = field(default_factory=list)
    loss_queue: list[tuple[str, str]] = field(default_factory=list)
    continuation: CoupContinuation | None = None
    exchange_draw: list[Card] = field(default_factory=list)
    winner: str | None = None
    turn_number: int = 0
    interaction_id: int = 0
    turn_limit_reached: bool = False
    history: list[str] = field(default_factory=list)
