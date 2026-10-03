"""Many complete games with random and rule-based policies.

After every recorded entry we check invariants that must always hold, whatever
the policies do. This is how rule bugs that no hand-written scenario covers
tend to show up.
"""

import pytest
from helpers import FULL_DECK_SORTED, all_cards

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.games.coup import CoupEnv, CoupHeuristicPolicy
from selfplay_worlds.policies import RandomPolicy


def _check_invariants(env) -> None:
    state = env.get_state(view="full")
    assert all_cards(env) == FULL_DECK_SORTED  # the 15 cards are never created or destroyed
    for p in state["players"]:
        assert p["coins"] >= 0
        assert len(p["hidden"]) + len(p["revealed"]) <= 2
        if not p["hidden"]:
            assert p["coins"] == 0  # eliminated players return their coins
    phase = env.get_dialogue_phase()
    assert state["done"] is (phase is None)
    if phase is not None:
        alive = {p["id"] for p in state["players"] if p["hidden"]}
        assert set(phase.eligible) <= alive  # the eliminated never act
        assert phase.eligible  # an open phase always has someone to ask


def _players(kind: str, num_players: int, seed: int):
    if kind == "random":
        return {f"p{i}": RandomPolicy(game_name="coup", seed=seed * 10 + i) for i in range(num_players)}
    return {f"p{i}": CoupHeuristicPolicy(seed=seed * 10 + i) for i in range(num_players)}


@pytest.mark.parametrize("kind", ["random", "heuristic"])
@pytest.mark.parametrize("num_players", [2, 3, 4, 5, 6])
def test_games_terminate_and_invariants_hold(kind, num_players):
    for seed in range(50):
        env = CoupEnv(game_config={"num_players": num_players, "seed": seed})
        game = ConversationGame(
            env=env,
            players=_players(kind, num_players, seed),
            max_attempts=5_000,
            on_entry=lambda entry, env=env: _check_invariants(env),
        )
        final = game.run()
        alive = [p["id"] for p in env.get_state(view="full")["players"] if p["hidden"]]
        assert final["termination_reason"] == "last_player_with_influence"  # the turn limit is never needed here
        assert final["winners"] == alive and len(alive) == 1
        assert env.get_dialogue_phase() is None
