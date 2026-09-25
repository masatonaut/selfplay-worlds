"""One episode -> one versioned JSON file."""

import json

from selfplay_worlds.agents.scripted import ScriptedAgent
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.episodes.log import SCHEMA_VERSION, EpisodeLogger
from selfplay_worlds.games import get_game

TOP_LEVEL_KEYS = {
    "schema_version",
    "game",
    "episode_id",
    "created_at",
    "seed",
    "config",
    "players",
    "initial_state",
    "events",
    "public_log",
    "result",
}
EVENT_KEYS = {
    "index",
    "kind",
    "interaction",
    "actor",
    "player_observation",
    "output",
    "auto",
    "fallback",
    "attempt",
    "accepted",
    "error",
    "public_events",
}


def _episode(*, include_full_state=False, seed=3):
    spec = get_game("coup")
    agents = {f"p{i}": ScriptedAgent(policy=spec.scripted_policy, seed=10 + i) for i in range(3)}
    logger = EpisodeLogger(include_full_state=include_full_state)
    Runner().run(env=spec.make_env(num_players=3), agents=agents, seed=seed, logger=logger)
    return logger


def test_record_has_the_documented_shape():
    record = _episode().record
    assert set(record) == TOP_LEVEL_KEYS
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["game"] == "coup"
    assert record["episode_id"] == "coup-seed3-3p"
    assert [p["id"] for p in record["players"]] == ["p0", "p1", "p2"]
    assert record["players"][0]["agent"] == {"type": "ScriptedAgent", "policy": "heuristic_policy", "model": None, "backend": None}
    assert all(set(e) == EVENT_KEYS for e in record["events"])
    assert [e["index"] for e in record["events"]] == list(range(len(record["events"])))


def test_every_event_separates_message_action_and_raw_output():
    for event in _episode().record["events"]:
        assert set(event["output"]) == {"message", "action", "raw_model_output", "metadata"}


def test_full_state_is_left_out_by_default():
    record = _episode().record
    assert record["config"]["include_full_state"] is False
    assert record["initial_state"]["full_state"] is None
    assert all("full_state_after" not in e for e in record["events"])


def test_full_state_can_be_switched_on():
    record = _episode(include_full_state=True).record
    assert record["initial_state"]["full_state"]["deck"]
    assert all("full_state_after" in e for e in record["events"])


def test_history_is_stored_once_not_in_every_event():
    record = _episode().record
    for event in record["events"]:
        assert "history" not in event["player_observation"]
        assert "history_length" in event["player_observation"]
    assert record["public_log"][0].startswith("Game starts with 3 players.")


def test_result_summary():
    record = _episode().record
    result = record["result"]
    assert len(result["winners"]) == 1
    assert result["num_events"] == len(record["events"])
    assert result["num_agent_calls"] == sum(1 for e in record["events"] if not e["auto"] and not e["fallback"])
    assert result["final_public_state"]["phase"] is None


def test_save_and_load_round_trip(tmp_path):
    logger = _episode(include_full_state=True)
    path = logger.save(tmp_path / "runs" / "episode.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == json.loads(json.dumps(logger.record))
