"""Coup cards and the action table. Source: docs/coup-rules.md."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Card(StrEnum):
    DUKE = "duke"
    ASSASSIN = "assassin"
    CAPTAIN = "captain"
    AMBASSADOR = "ambassador"
    CONTESSA = "contessa"

    @property
    def label(self) -> str:
        return "the " + self.value.capitalize()


FULL_DECK: list[Card] = [card for card in Card for _ in range(3)]  # 15 cards


@dataclass(frozen=True)
class ActionRule:
    name: str
    cost: int
    claim: Card | None
    """Character the actor must claim, or None for a general action."""
    blockers: tuple[Card, ...]
    """Characters that can block this action."""
    targeted: bool
    block_by_anyone: bool
    """Foreign Aid can be blocked by any player; Steal and Assassinate only by the target."""


ACTIONS: dict[str, ActionRule] = {
    "income": ActionRule("income", 0, None, (), False, False),
    "foreign_aid": ActionRule("foreign_aid", 0, None, (Card.DUKE,), False, True),
    "coup": ActionRule("coup", 7, None, (), True, False),
    "tax": ActionRule("tax", 0, Card.DUKE, (), False, False),
    "assassinate": ActionRule("assassinate", 3, Card.ASSASSIN, (Card.CONTESSA,), True, False),
    "steal": ActionRule("steal", 0, Card.CAPTAIN, (Card.CAPTAIN, Card.AMBASSADOR), True, False),
    "exchange": ActionRule("exchange", 0, Card.AMBASSADOR, (), False, False),
}

COUP_COST = 7
FORCED_COUP_COINS = 10
