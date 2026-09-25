"""Many complete games with random and rule-based agents.

After every single step we check invariants that must always hold, whatever
the agents do. This is how rule bugs that no hand-written scenario covers
tend to show up.
"""

import pytest
from helpers import FULL_DECK_SORTED, all_cards

from selfplay_worlds.agents.scripted import RandomAgent, ScriptedAgent
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.games import get_game


def _check_invariants(env) -> None:
    state = env.full_state()
    assert all_cards(env) == FULL_DECK_SORTED  # the 15 cards are never created or destroyed
    for p in state["players"]:
        assert p["coins"] >= 0
        assert len(p["hidden"]) + len(p["revealed"]) <= 2
        if not p["hidden"]:
            assert p["coins"] == 0  # eliminated players return their coins
    interaction = env.current_interaction()
    if interaction is not None:
        alive = {p["id"] for p in state["players"] if p["hidden"]}
        assert set(interaction.eligible_players) <= alive  # the eliminated never act
        assert interaction.eligible_players  # an open interaction always has someone to ask


def _agents(kind: str, num_players: int, seed: int):
    spec = get_game("coup")
    if kind == "random":
        return {f"p{i}": RandomAgent(seed=seed * 10 + i) for i in range(num_players)}
    return {f"p{i}": ScriptedAgent(policy=spec.scripted_policy, seed=seed * 10 + i) for i in range(num_players)}


@pytest.mark.parametrize("kind", ["random", "heuristic"])
@pytest.mark.parametrize("num_players", [2, 3, 4, 5, 6])
def test_games_terminate_and_invariants_hold(kind, num_players):
    for seed in range(50):
        env = get_game("coup").make_env(num_players=num_players)
        runner = Runner(on_event=lambda event, env=env: _check_invariants(env), max_steps=5_000)
        result = runner.run(env=env, agents=_agents(kind, num_players, seed), seed=seed)
        alive = [p["id"] for p in env.full_state()["players"] if p["hidden"]]
        assert result.termination_reason == "last_player_with_influence"  # the turn limit is never needed here
        assert result.winners == alive and len(alive) == 1
        assert env.current_interaction() is None
