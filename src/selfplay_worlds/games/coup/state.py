"""Serializable source of truth for one Coup game."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from selfplay_worlds.games.coup.actions import CoupActionType
from selfplay_worlds.games.coup.cards import Card


class CoupPhase(StrEnum):
    ACTION = "action"
    CHALLENGE_ACTION = "challenge_action"
    BLOCK_ACTION = "block_action"
    CHALLENGE_BLOCK = "challenge_block"
    LOSE_INFLUENCE = "lose_influence"
    EXCHANGE = "exchange"


def _tuples(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuples(item) for item in value)
    return value


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "coins": self.coins,
            "hidden": [card.value for card in self.hidden],
            "revealed": [card.value for card in self.revealed],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoupPlayerState:
        return cls(
            id=data["id"],
            name=data["name"],
            coins=data["coins"],
            hidden=[Card(card) for card in data["hidden"]],
            revealed=[Card(card) for card in data["revealed"]],
        )


@dataclass
class CoupTurnState:
    actor: str
    action: CoupActionType | None = None
    target: str | None = None
    paid: int = 0
    blocker: str | None = None
    block_claim: Card | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action.value if self.action else None,
            "target": self.target,
            "paid": self.paid,
            "blocker": self.blocker,
            "block_claim": self.block_claim.value if self.block_claim else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoupTurnState:
        return cls(
            actor=data["actor"],
            action=CoupActionType(data["action"]) if data["action"] else None,
            target=data["target"],
            paid=data["paid"],
            blocker=data["blocker"],
            block_claim=Card(data["block_claim"]) if data["block_claim"] else None,
        )


@dataclass
class CoupState:
    players: list[CoupPlayerState]
    deck: list[Card]
    current_turn: CoupTurnState | None
    phase: CoupPhase | None
    eligible_players: list[str]
    loss_queue: list[tuple[str, str]]
    continuation: str | None
    exchange_draw: list[Card]
    winner: str | None
    turn_number: int
    interaction_id: int
    turn_limit_reached: bool
    start_player: str
    history: list[str]
    rng_state: tuple[Any, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "players": [player.to_dict() for player in self.players],
            "deck": [card.value for card in self.deck],
            "current_turn": self.current_turn.to_dict() if self.current_turn else None,
            "phase": self.phase.value if self.phase else None,
            "eligible_players": list(self.eligible_players),
            "loss_queue": [list(item) for item in self.loss_queue],
            "continuation": self.continuation,
            "exchange_draw": [card.value for card in self.exchange_draw],
            "winner": self.winner,
            "turn_number": self.turn_number,
            "interaction_id": self.interaction_id,
            "turn_limit_reached": self.turn_limit_reached,
            "start_player": self.start_player,
            "history": list(self.history),
            "rng_state": self.rng_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoupState:
        return cls(
            players=[CoupPlayerState.from_dict(player) for player in data["players"]],
            deck=[Card(card) for card in data["deck"]],
            current_turn=CoupTurnState.from_dict(data["current_turn"]) if data["current_turn"] else None,
            phase=CoupPhase(data["phase"]) if data["phase"] else None,
            eligible_players=list(data["eligible_players"]),
            loss_queue=[tuple(item) for item in data["loss_queue"]],
            continuation=data["continuation"],
            exchange_draw=[Card(card) for card in data["exchange_draw"]],
            winner=data["winner"],
            turn_number=data["turn_number"],
            interaction_id=data["interaction_id"],
            turn_limit_reached=data["turn_limit_reached"],
            start_player=data["start_player"],
            history=list(data["history"]),
            rng_state=_tuples(data["rng_state"]),
        )
