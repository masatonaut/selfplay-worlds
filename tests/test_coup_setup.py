"""Setup (reset) and seeded determinism."""

import pytest
from helpers import FULL_DECK_SORTED, all_cards, coins, hidden, history, new_game

from selfplay_worlds.core.env import DialogueMode
from selfplay_worlds.games.coup import CoupEnv


@pytest.mark.parametrize("num_players", [2, 3, 4, 5, 6])
def test_reset_deals_two_cards_and_keeps_the_rest_in_the_deck(num_players):
    env = CoupEnv(game_config={"num_players": num_players, "seed": 1})
    state = env.get_state(view="full")
    assert all(len(p["hidden"]) == 2 and p["revealed"] == [] for p in state["players"])
    assert len(state["deck"]) == 15 - 2 * num_players
    assert all_cards(env) == FULL_DECK_SORTED


def test_reset_gives_two_coins_each_with_three_players():
    env = CoupEnv(game_config={"num_players": 3, "seed": 1})
    assert [coins(env, pid) for pid in env.player_ids] == [2, 2, 2]


def test_two_player_game_gives_the_starting_player_one_coin():
    env = CoupEnv(game_config={"num_players": 2, "starting_player": "p1", "seed": 1})
    assert coins(env, "p1") == 1
    assert coins(env, "p0") == 2


def test_first_interaction_is_the_starting_players_action():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}, start="p1")
    interaction = env.get_dialogue_phase()
    assert interaction.phase == "action"
    assert interaction.mode is DialogueMode.ACTION
    assert interaction.eligible == ("p1",)
    assert history(env)[0] == "Game starts with 3 players. Bob goes first."


def test_initial_hands_are_used_and_removed_from_the_deck():
    env = new_game({"p0": ["duke", "duke"], "p1": ["duke", "captain"], "p2": ["contessa", "assassin"]})
    assert hidden(env, "p0") == ["duke", "duke"]
    assert "duke" not in env.get_state(view="full")["deck"]
    assert all_cards(env) == FULL_DECK_SORTED


@pytest.mark.parametrize("num_players", [1, 7])
def test_unsupported_player_counts_are_rejected(num_players):
    with pytest.raises(ValueError):
        CoupEnv(game_config={"num_players": num_players})


def test_wrong_number_of_names_is_rejected():
    with pytest.raises(ValueError, match="expected 4 names"):
        CoupEnv(game_config={"num_players": 4, "names": ["Ann", "Ben"]})


def test_same_seed_gives_the_same_game():
    a = CoupEnv(game_config={"num_players": 4, "seed": 123})
    b = CoupEnv(game_config={"num_players": 4, "seed": 123})
    assert a.get_state(view="full") == b.get_state(view="full")


def test_different_seeds_give_different_deals():
    deals = set()
    for seed in range(10):
        env = CoupEnv(game_config={"num_players": 4, "seed": seed})
        deals.add(repr(env.get_state(view="full")["players"]))
    assert len(deals) > 1
