"""The GameEnv contract: config, reset, n_steps, get_state keys, pickle save and load."""

import pytest
from fixtures.talk_then_vote import TalkThenVoteEnv
from helpers import act, history, new_game

from selfplay_worlds.core.env import config_mismatches
from selfplay_worlds.games.coup import CoupEnv

HANDS = {"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}

ENVS = {
    "coup": lambda: CoupEnv(game_config={"num_players": 3, "seed": 4}),
    "fixture": lambda: TalkThenVoteEnv(game_config={"rounds": 1}),
}


@pytest.mark.parametrize("make_env", ENVS.values(), ids=ENVS.keys())
def test_init_stores_name_and_config_and_resets(make_env):
    env = make_env()
    assert env.name and isinstance(env.game_config, dict)
    assert env.n_steps == 0
    assert env.get_dialogue_phase() is not None  # reset() ran at the end of __init__


@pytest.mark.parametrize("make_env", ENVS.values(), ids=ENVS.keys())
@pytest.mark.parametrize("view", ["public", "full"])
def test_get_state_always_has_done_and_rewards(make_env, view):
    env = make_env()
    state = env.get_state(view=view)
    assert state["done"] is False
    assert state["rewards"] == {pid: 0.0 for pid in env.player_ids}


@pytest.mark.parametrize("make_env", ENVS.values(), ids=ENVS.keys())
def test_observation_has_history_and_a_menu_of_options(make_env):
    env = make_env()
    acting = env.get_dialogue_phase().eligible[0]
    observation = env.get_observation(player_id=acting)
    assert isinstance(observation["history"], list)
    assert observation["options"]


def test_coup_config_is_completed_with_defaults_and_rejects_unknown_settings():
    env = CoupEnv(game_config={"num_players": 4})
    assert env.game_config["names"] == ["Alice", "Bob", "Carol", "Dave"]
    assert env.game_config["max_turns"] == 100 and env.game_config["seed"] is None
    with pytest.raises(ValueError, match="unknown Coup settings"):
        CoupEnv(game_config={"num_players": 3, "speed": "fast"})


def test_config_mismatches_reports_missing_extra_and_different_keys():
    assert config_mismatches(saved={"a": 1, "b": 2}, current={"a": 1, "b": 2}) == []
    assert config_mismatches(saved={"a": 1, "b": 2, "c": 3}, current={"a": 9, "b": 2, "d": 4}) == ["a", "c", "d"]


def test_save_and_load_round_trip_keeps_state_rng_and_n_steps(tmp_path):
    env = new_game(HANDS, seed=11)
    act(env, "p0", "tax")
    path = env.save(path=tmp_path / "env.pkl")

    restored = new_game(HANDS, seed=11)
    restored.load(path=path)
    assert restored.get_state(view="full") == env.get_state(view="full")
    assert restored.n_steps == env.n_steps == 1
    # Alice really has the Duke: the challenge shuffles the deck, so the RNG must match too.
    for game in (env, restored):
        act(game, "p1", "challenge")
    assert restored.get_state(view="full") == env.get_state(view="full")
    assert history(restored) == history(env)


def test_load_refuses_a_different_game_config(tmp_path):
    path = new_game(HANDS, seed=1).save(path=tmp_path / "env.pkl")
    other = new_game(HANDS, seed=2, start="p1")
    with pytest.raises(ValueError, match=r"\['seed', 'starting_player'\]"):
        other.load(path=path)


def test_load_refuses_a_different_environment_class(tmp_path):
    path = TalkThenVoteEnv().save(path=tmp_path / "env.pkl")
    with pytest.raises(TypeError, match="TalkThenVoteEnv"):
        CoupEnv().load(path=path)
