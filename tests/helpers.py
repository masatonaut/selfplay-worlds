"""Small helpers shared by the tests. No LLM, no network, no GPU."""

from __future__ import annotations

from selfplay_worlds.core.types import AgentOutput, StepResult
from selfplay_worlds.games.coup import CoupEnv
from selfplay_worlds.games.coup.cards import FULL_DECK


def new_game(
    hands: dict[str, list[str]],
    *,
    coins: dict[str, int] | None = None,
    start: str = "p0",
    seed: int = 0,
    num_players: int | None = None,
) -> CoupEnv:
    """A Coup game with a fixed opening position."""
    env = CoupEnv(
        num_players=num_players or len(hands),
        initial_hands=hands,
        initial_coins=coins,
        starting_player=start,
    )
    env.reset(seed=seed)
    return env


def act(env, player_id: str, action_type: str, *, message: str | None = None, **fields) -> StepResult:
    """Step the environment with one action and fail the test if it is rejected."""
    output = AgentOutput(action={"type": action_type, **fields}, message=message)
    result = env.step(player_id=player_id, output=output)
    assert result.accepted, result.error
    return result


def phase(env) -> str | None:
    interaction = env.current_interaction()
    return None if interaction is None else interaction.phase


def eligible(env) -> list[str]:
    return list(env.current_interaction().eligible_players)


def player(env, player_id: str) -> dict:
    """God view of one player (hidden cards included). Tests only."""
    return {p["id"]: p for p in env.full_state()["players"]}[player_id]


def coins(env, player_id: str) -> int:
    return player(env, player_id)["coins"]


def hidden(env, player_id: str) -> list[str]:
    return player(env, player_id)["hidden"]


def revealed(env, player_id: str) -> list[str]:
    return player(env, player_id)["revealed"]


def all_cards(env) -> list[str]:
    """Every card in the game, wherever it is. Always the full 15-card deck."""
    state = env.full_state()
    cards = list(state["deck"]) + list(state["exchange_draw"])
    for p in state["players"]:
        cards += p["hidden"] + p["revealed"]
    return sorted(cards)


FULL_DECK_SORTED = sorted(card.value for card in FULL_DECK)
