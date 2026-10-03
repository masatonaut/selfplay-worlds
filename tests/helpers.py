"""Small helpers shared by the tests. No LLM, no network, no GPU."""

from __future__ import annotations

from selfplay_worlds.core.env import StepResult
from selfplay_worlds.games.coup import CoupAction, CoupEnv
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
    return CoupEnv(
        game_config={
            "num_players": num_players or len(hands),
            "initial_hands": hands,
            "initial_coins": coins,
            "starting_player": start,
            "seed": seed,
        }
    )


def act(env, player_id: str, action_type: str, **fields) -> StepResult:
    """Step the environment with one action and fail the test if it is rejected."""
    result = env.step(player_id=player_id, action=CoupAction.from_dict({"type": action_type, **fields}))
    assert result.accepted, result.error
    return result


def phase(env) -> str | None:
    current = env.get_dialogue_phase()
    return None if current is None else current.phase


def eligible(env) -> list[str]:
    return list(env.get_dialogue_phase().eligible)


def history(env) -> list[str]:
    return env.get_state()["history"]


def player(env, player_id: str) -> dict:
    """God view of one player (hidden cards included). Tests only."""
    return {p["id"]: p for p in env.get_state(view="full")["players"]}[player_id]


def coins(env, player_id: str) -> int:
    return player(env, player_id)["coins"]


def hidden(env, player_id: str) -> list[str]:
    return player(env, player_id)["hidden"]


def revealed(env, player_id: str) -> list[str]:
    return player(env, player_id)["revealed"]


def all_cards(env) -> list[str]:
    """Every card in the game, wherever it is. Always the full 15-card deck."""
    state = env.get_state(view="full")
    cards = list(state["deck"]) + list(state["exchange_draw"])
    for p in state["players"]:
        cards += p["hidden"] + p["revealed"]
    return sorted(cards)


FULL_DECK_SORTED = sorted(card.value for card in FULL_DECK)
