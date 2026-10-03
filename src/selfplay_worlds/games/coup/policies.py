"""Rule-based Coup policy.

Its job is to exercise the interesting mechanics (claims, bluffs, challenges,
blocks, table talk) so the demo and tests show the framework working. It is not
meant to be a strong player. All randomness comes from the policy's seeded RNG.

Talk and action are decided together: ``get_message`` makes the decision and
remembers it, and ``step`` plays the remembered answer for the same decision.
"""

from __future__ import annotations

from typing import Any

from selfplay_worlds.policies.scripted import ScriptedPolicy

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

Decision = tuple[dict[str, Any], str | None]
"""(answer, message)"""


class CoupHeuristicPolicy(ScriptedPolicy):
    def __init__(self, *, seed: int = 0) -> None:
        super().__init__(game_name="coup", seed=seed)
        self._planned: tuple[int, dict[str, Any]] | None = None

    def get_message(self, *, observation, conversation):
        answer, message = self._decide(observation)
        self._planned = (observation["decision_id"], answer)
        return message

    def step(self, *, observation, conversation):
        planned, self._planned = self._planned, None
        if planned is not None and planned[0] == observation["decision_id"] and "feedback" not in observation:
            return planned[1]
        return self._decide(observation)[0]

    def _decide(self, obs: dict[str, Any]) -> Decision:
        phase, options = obs["phase"], obs["options"]
        if phase == "action":
            return _choose_action(obs, options, self.rng)
        if phase in ("challenge_action", "challenge_block"):
            return _maybe_challenge(obs, phase, self.rng)
        if phase == "block_action":
            return _maybe_block(obs, options, self.rng)
        if phase == "lose_influence":
            return _least_valuable_reveal(options), None
        if phase == "exchange":
            return _best_keep(options), None
        return {"option": 1}, None


def _choose_action(obs: dict, options: list[dict], rng) -> Decision:
    mine = set(obs["your_cards"])
    coins = obs["your_coins"]
    opponents = [p for p in obs["players"] if p["alive"] and p["id"] != obs["you"]]
    strongest = max(opponents, key=lambda p: (p["hidden_card_count"], p["coins"]))["id"]
    richest = max(opponents, key=lambda p: p["coins"])
    available = {option["type"] for option in options}

    def act(kind: str, target: str | None = None) -> Decision:
        answer = {"type": kind} if target is None else {"type": kind, "target": target}
        line = CLAIM_LINES.get(kind) if rng.random() < TALK_RATE else None
        return answer, line

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


def _maybe_challenge(obs: dict, phase: str, rng) -> Decision:
    pending = obs["pending_action"]
    claim = pending["block_claim"] if phase == "challenge_block" else pending["claim"]
    seen = obs["your_cards"].count(claim) + sum(p["revealed_cards"].count(claim) for p in obs["players"])
    if seen >= 3:
        return {"type": "challenge"}, "All three of those are already accounted for."
    if len(obs["your_cards"]) == 1:
        return {"type": "pass"}, None  # too risky without certainty
    targeted = pending["target"] == obs["you"] and phase == "challenge_action"
    rate = CHALLENGE_RATE * (2 if targeted else 1)
    if rng.random() < rate:
        message = "I don't believe you." if rng.random() < TALK_RATE else None
        return {"type": "challenge"}, message
    return {"type": "pass"}, None


def _maybe_block(obs: dict, options: list[dict], rng) -> Decision:
    mine = set(obs["your_cards"])
    for option in options:
        if option["type"] == "block" and option["claim"] in mine:
            return option, None
    if obs["pending_action"]["action"] == "assassinate" and len(obs["your_cards"]) == 1 and rng.random() < 0.5:
        contessa = next(o for o in options if o["type"] == "block" and o["claim"] == "contessa")
        return contessa, "I have the Contessa."
    return {"type": "pass"}, None


def _least_valuable_reveal(options: list[dict]) -> dict:
    return max(options, key=lambda option: KEEP_PRIORITY.index(option["card"]))


def _best_keep(options: list[dict]) -> dict:
    return min(options, key=lambda option: sum(KEEP_PRIORITY.index(card) for card in option["cards"]))
