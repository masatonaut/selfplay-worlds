"""How Coup is described to an LLM agent. Game-specific text lives here, not in the agent."""

from __future__ import annotations

import json

RULES_TEXT = """You are playing Coup, a bluffing card game. The last player with any face-down cards wins.

Each player has hidden character cards (influence) and coins. On your turn you take exactly one action:
- income: +1 coin.
- foreign_aid: +2 coins. Any player may block it by claiming the Duke.
- coup: pay 7 coins, the target loses one card. Cannot be blocked. Mandatory if you start your turn with 10+ coins.
- tax (claim Duke): +3 coins.
- assassinate (claim Assassin): pay 3 coins, the target loses one card. The target may block by claiming the Contessa.
- steal (claim Captain): take 2 coins from the target. The target may block by claiming the Captain or Ambassador.
- exchange (claim Ambassador): draw 2 cards, keep as many as you had, return the rest.

You may claim a character you do not have (bluff). Any other player may challenge a claim, including a block.
If challenged and you really have the card, you reveal it, shuffle it back and draw a new card, and the challenger loses a card.
If you do not have it, you lose a card and your action or block fails. A successfully challenged action refunds its cost; a blocked action does not.
When you lose a card, you choose which one to reveal. With no cards left you are out.
You may also say something to the table. Talk is public and never binding."""

HISTORY_WINDOW = 40


def render_observation(*, observation: dict, interaction, legal_actions: list[dict]) -> str:
    lines = [
        f"You are {observation['your_name']} ({observation['you']}).",
        f"Your hidden cards: {', '.join(observation['your_cards']) or 'none'}. Your coins: {observation['your_coins']}.",
    ]
    if "exchange_drawn" in observation:
        lines.append(f"You drew from the Court deck: {', '.join(observation['exchange_drawn'])}.")
    lines.append("")
    lines.append("Players:")
    for p in observation["players"]:
        status = "out" if not p["alive"] else f"{p['hidden_card_count']} hidden card(s)"
        revealed = ", ".join(p["revealed_cards"]) or "none"
        you = "  <- you" if p["id"] == observation["you"] else ""
        lines.append(f"- {p['name']} ({p['id']}): {p['coins']} coins, {status}, revealed: {revealed}{you}")
    lines.append(f"Court deck: {observation['deck_size']} cards.")
    history = observation.get("history", [])[-HISTORY_WINDOW:]
    lines.append("")
    lines.append(f"Recent events (last {len(history)}):")
    lines.extend(f"- {h}" for h in history)
    lines.append("")
    lines.append(f"Current decision [{interaction.phase}]: {interaction.description}")
    lines.append("Legal actions:")
    lines.extend(f"{i}. {json.dumps(a)}" for i, a in enumerate(legal_actions, 1))
    return "\n".join(lines)
