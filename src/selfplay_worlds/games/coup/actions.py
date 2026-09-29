"""Typed actions owned by Coup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from selfplay_worlds.games.coup.cards import Card


class CoupActionType(StrEnum):
    INCOME = "income"
    FOREIGN_AID = "foreign_aid"
    COUP = "coup"
    TAX = "tax"
    ASSASSINATE = "assassinate"
    STEAL = "steal"
    EXCHANGE = "exchange"
    PASS = "pass"
    CHALLENGE = "challenge"
    BLOCK = "block"
    REVEAL = "reveal"
    KEEP = "keep"


@dataclass(frozen=True)
class CoupAction:
    """One structurally valid Coup action.

    Game legality still belongs to :class:`CoupEnv`.
    """

    type: CoupActionType
    target: str | None = None
    claim: Card | None = None
    card: Card | None = None
    cards: tuple[Card, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type.value}
        if self.target is not None:
            data["target"] = self.target
        if self.claim is not None:
            data["claim"] = self.claim.value
        if self.card is not None:
            data["card"] = self.card.value
        if self.cards:
            data["cards"] = [card.value for card in self.cards]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CoupAction:
        """Parse structure only.  Unknown or inconsistent fields are rejected."""
        if not isinstance(data, Mapping):
            raise TypeError("a Coup action must be an object")
        try:
            action_type = CoupActionType(data["type"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("a Coup action needs a known 'type'") from error

        allowed: dict[CoupActionType, set[str]] = {
            CoupActionType.COUP: {"type", "target"},
            CoupActionType.ASSASSINATE: {"type", "target"},
            CoupActionType.STEAL: {"type", "target"},
            CoupActionType.BLOCK: {"type", "claim"},
            CoupActionType.REVEAL: {"type", "card"},
            CoupActionType.KEEP: {"type", "cards"},
        }
        keys = set(data)
        expected = allowed.get(action_type, {"type"})
        if keys != expected:
            raise ValueError(f"{action_type.value!r} action fields must be {sorted(expected)}")

        target = data.get("target")
        if "target" in expected and (not isinstance(target, str) or not target):
            raise ValueError("target must be a non-empty player id")
        claim = Card(data["claim"]) if "claim" in expected else None
        card = Card(data["card"]) if "card" in expected else None
        raw_cards = data.get("cards", [])
        if "cards" in expected and not isinstance(raw_cards, list):
            raise ValueError("cards must be a list")
        cards = tuple(sorted((Card(value) for value in raw_cards), key=lambda value: value.value))
        if "cards" in expected and not cards:
            raise ValueError("cards must not be empty")
        return cls(type=action_type, target=target, claim=claim, card=card, cards=cards)

def coup_action(action_type: CoupActionType | str, **fields: Any) -> CoupAction:
    return CoupAction.from_dict({"type": str(action_type), **fields})
