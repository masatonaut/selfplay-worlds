"""Observations must contain exactly what the player may know."""

import json

from helpers import act, new_game

from selfplay_worlds.games.coup import CoupEnv

HIDDEN_ONLY_KEYS = {"hidden", "deck", "loss_queue", "exchange_draw", "winner", "eligible"}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


def test_observation_shows_own_cards_but_only_counts_for_others():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    obs = env.observe(player_id="p0")
    assert obs["your_cards"] == ["duke", "captain"]
    assert obs["your_coins"] == 2
    for p in obs["players"]:
        assert set(p) == {"id", "name", "coins", "alive", "hidden_card_count", "revealed_cards"}
    assert not (_keys(obs) & HIDDEN_ONLY_KEYS)


def test_observation_does_not_depend_on_other_players_hidden_cards():
    """Two games that differ only in Bob's and Carol's cards look identical to Alice."""
    a = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    b = new_game({"p0": ["duke", "captain"], "p1": ["ambassador", "ambassador"], "p2": ["contessa", "contessa"]})
    assert a.observe(player_id="p0") == b.observe(player_id="p0")
    for env in (a, b):
        act(env, "p0", "income")
        act(env, "p1", "foreign_aid")
        act(env, "p2", "pass")
        act(env, "p0", "pass")
    assert a.observe(player_id="p0") == b.observe(player_id="p0")


def test_public_history_does_not_reveal_the_replacement_card():
    """After a won challenge the claimant draws a new card. Different seeds draw
    different cards, but everyone else sees exactly the same history."""
    replacements, histories = set(), set()
    for seed in range(20):
        env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}, seed=seed)
        act(env, "p0", "tax")
        act(env, "p1", "challenge")  # Alice really has the Duke
        replacements.add(env.full_state()["players"][0]["hidden"][1])
        histories.add(tuple(env.public_history()))
        assert env.observe(player_id="p1")["players"][0]["hidden_card_count"] == 2
    assert len(replacements) > 1
    assert len(histories) == 1


def test_exchange_draw_is_visible_only_to_the_ambassador():
    env = new_game({"p0": ["ambassador", "captain"], "p1": ["contessa", "assassin"], "p2": ["duke", "duke"]})
    act(env, "p0", "exchange")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    assert env.current_interaction().phase == "exchange"
    assert len(env.observe(player_id="p0")["exchange_drawn"]) == 2
    assert "exchange_drawn" not in env.observe(player_id="p1")
    assert "exchange_drawn" not in env.observe(player_id="p2")


def test_observation_is_json_serialisable():
    env = CoupEnv(num_players=5)
    env.reset(seed=3)
    json.dumps(env.observe(player_id="p2"))
