"""Rule-based Coup policy for deterministic ScriptedAgents.

Its job is to exercise the interesting mechanics (claims, bluffs, challenges,
blocks, table talk) so the demo and tests show the framework working. It is not
meant to be a strong player. All randomness comes from the seeded ``rng``.
"""

from __future__ import annotations

from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.games.coup.actions import CoupAction, CoupActionType

KEEP_PRIORITY = ["duke", "assassin", "captain", "contessa", "ambassador"]  # most valuable first
BLUFF_RATE = 0.25
CHALLENGE_RATE = 0.2
TALK_RATE = 0.35

CLAIM_LINES = {
    "tax": "I'm the Duke. Three coins for me.",
    "steal": "My Captain will take those coins.",
    "assassinate": "Nothing personal.",
    "exchange": "Let me see what the Court has.",
}


def heuristic_policy(*, observation: dict, interaction, legal_actions: list[CoupAction], rng) -> AgentOutput:
    phase = interaction.phase
    if phase == "action":
        return _choose_action(observation, legal_actions, rng)
    if phase in ("challenge_action", "challenge_block"):
        return _maybe_challenge(observation, interaction.phase, rng)
    if phase == "block_action":
        return _maybe_block(observation, legal_actions, rng)
    if phase == "lose_influence":
        return AgentOutput(action=_least_valuable_reveal(legal_actions))
    if phase == "exchange":
        return AgentOutput(action=_best_keep(legal_actions))
    return AgentOutput(action=legal_actions[0])


def _choose_action(obs: dict, legal: list[CoupAction], rng) -> AgentOutput:
    mine = set(obs["your_cards"])
    coins = obs["your_coins"]
    opponents = [p for p in obs["players"] if p["alive"] and p["id"] != obs["you"]]
    strongest = max(opponents, key=lambda p: (p["hidden_card_count"], p["coins"]))["id"]
    richest = max(opponents, key=lambda p: p["coins"])
    available = {action.type.value for action in legal}

    def act(kind: str, target: str | None = None) -> AgentOutput:
        action = CoupAction(CoupActionType(kind), target=target)
        line = CLAIM_LINES.get(kind) if rng.random() < TALK_RATE else None
        return AgentOutput(action=action, message=line)

    if "coup" in available and coins >= 7:
        return act("coup", strongest)
    if "assassinate" in available and "assassin" in mine:
        return act("assassinate", strongest)
    if "duke" in mine:
        return act("tax")
    if "captain" in mine and richest["coins"] >= 2 and richest["coins"] > coins:
        # Only from someone richer: two lone Captains stealing from each other and
        # blocking would otherwise repeat forever.
        return act("steal", richest["id"])
    if rng.random() < BLUFF_RATE:
        if "assassinate" in available and rng.random() < 0.3:
            return act("assassinate", strongest)
        return act("tax")
    if "ambassador" in mine and rng.random() < 0.4:
        return act("exchange")
    return act("foreign_aid") if rng.random() < 0.5 else act("income")


def _maybe_challenge(obs: dict, phase: str, rng) -> AgentOutput:
    pending = obs["pending_action"]
    claim = pending["block_claim"] if phase == "challenge_block" else pending["claim"]
    seen = obs["your_cards"].count(claim) + sum(p["revealed_cards"].count(claim) for p in obs["players"])
    if seen >= 3:
        return AgentOutput(action=CoupAction(CoupActionType.CHALLENGE), message="All three of those are already accounted for.")
    my_cards = len(obs["your_cards"])
    if my_cards == 1:
        return AgentOutput(action=CoupAction(CoupActionType.PASS))  # too risky without certainty
    targeted = pending["target"] == obs["you"] and phase == "challenge_action"
    rate = CHALLENGE_RATE * (2 if targeted else 1)
    if rng.random() < rate:
        message = "I don't believe you." if rng.random() < TALK_RATE else None
        return AgentOutput(action=CoupAction(CoupActionType.CHALLENGE), message=message)
    return AgentOutput(action=CoupAction(CoupActionType.PASS))


def _maybe_block(obs: dict, legal: list[CoupAction], rng) -> AgentOutput:
    mine = set(obs["your_cards"])
    for action in legal:
        if action.type is CoupActionType.BLOCK and action.claim.value in mine:
            return AgentOutput(action=action)
    pending = obs["pending_action"]
    if pending["action"] == "assassinate" and len(obs["your_cards"]) == 1 and rng.random() < 0.5:
        action = next(
            item
            for item in legal
            if item.type is CoupActionType.BLOCK and item.claim.value == "contessa"
        )
        return AgentOutput(action=action, message="I have the Contessa.")
    return AgentOutput(action=CoupAction(CoupActionType.PASS))


def _least_valuable_reveal(legal: list[CoupAction]) -> CoupAction:
    return max(legal, key=lambda action: KEEP_PRIORITY.index(action.card.value))


def _best_keep(legal: list[CoupAction]) -> CoupAction:
    return min(
        legal,
        key=lambda action: sum(KEEP_PRIORITY.index(card.value) for card in action.cards),
    )
