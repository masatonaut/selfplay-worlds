"""The LLM path, tested with MockBackend only. No network, no API key, no GPU."""

import importlib.util
import json

import pytest
from helpers import act, new_game

from selfplay_worlds.agents.llm_agent import LLMAgent, parse_reply
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.episodes.log import EpisodeLogger
from selfplay_worlds.games import get_game
from selfplay_worlds.inference import MockBackend

LEGAL = [{"type": "income"}, {"type": "tax"}, {"type": "steal", "target": "p1"}]


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"message": "Duke here.", "action": 2}', ("Duke here.", {"type": "tax"}, None)),
        ('{"message": null, "action": "3"}', (None, {"type": "steal", "target": "p1"}, None)),
        ('```json\n{"message": "", "action": 1}\n```', (None, {"type": "income"}, None)),
        ('I will play safe. {"action": 1, "message": "Income."} Done.', ("Income.", {"type": "income"}, None)),
        ('{"action": {"type": "tax"}}', (None, {"type": "tax"}, None)),
        ('{"message": "Just talking."}', ("Just talking.", None, None)),
        ("I take income.", (None, None, "no JSON object found in the reply")),
        ('{"action": 9}', (None, None, "action number 9 is not between 1 and 3")),
        ('{"action": true}', (None, None, "could not read the action True")),
    ],
)
def test_parse_reply(text, expected):
    assert parse_reply(text, LEGAL) == expected


def _llm_agents(backend_for_player):
    spec = get_game("coup")
    return {pid: LLMAgent(backend=backend_for_player(pid), spec=spec) for pid in ("p0", "p1", "p2")}


def test_full_game_with_llm_agents_on_a_mock_backend():
    agents = _llm_agents(lambda pid: MockBackend(respond=lambda messages: '{"message": null, "action": 1}'))
    logger = EpisodeLogger()
    result = Runner().run(env=get_game("coup").make_env(num_players=3), agents=agents, seed=1, logger=logger)
    assert len(result.winners) == 1
    record = logger.record
    assert record["players"][0]["agent"]["type"] == "LLMAgent"
    assert record["players"][0]["agent"]["backend"] == "mock"
    asked = [e for e in record["events"] if not e["auto"]]
    assert asked and all(e["output"]["raw_model_output"] == '{"message": null, "action": 1}' for e in asked)
    assert all(e["output"]["metadata"]["model"] == "mock" for e in asked)


def test_unreadable_reply_is_retried_with_an_explanation():
    backend = MockBackend(replies=["I take income.", '{"message": null, "action": 1}'], respond=lambda m: '{"action": 1}')
    agents = _llm_agents(lambda pid: backend if pid == "p0" else MockBackend(respond=lambda m: '{"action": 1}'))
    env = get_game("coup").make_env(num_players=3, starting_player="p0")
    steps = []
    Runner(on_event=steps.append).run(env=env, agents=agents, seed=0)
    first, second = steps[1], steps[2]
    assert first["accepted"] is False and first["error"] == "no action given"
    assert first["output"]["metadata"]["parse_error"] == "no JSON object found in the reply"
    assert second["accepted"] is True and second["attempt"] == 2
    retry_prompt = backend.calls[1][1]["content"]
    assert "Your previous reply was rejected: no action given (no JSON object found in the reply)" in retry_prompt


def test_prompt_contains_the_rules_the_situation_and_numbered_actions():
    backend = MockBackend(respond=lambda m: '{"action": 1}')
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    agent = LLMAgent(backend=backend, spec=get_game("coup"))
    interaction = env.current_interaction()
    agent.act(observation=env.observe(player_id="p0"), interaction=interaction, legal_actions=env.legal_actions(player_id="p0"))
    system, user = backend.calls[0][0]["content"], backend.calls[0][1]["content"]
    assert "You are playing Coup" in system
    assert "Your hidden cards: duke, captain." in user
    assert '1. {"type": "income"}' in user
    assert "A message is optional." in user


def test_prompt_never_depends_on_other_players_hidden_cards():
    """Carol's prompt is identical whatever Alice and Bob really hold."""
    prompts = []
    for others in (
        {"p0": ["duke", "captain"], "p1": ["contessa", "assassin"]},
        {"p0": ["captain", "captain"], "p1": ["contessa", "contessa"]},
    ):
        env = new_game({**others, "p2": ["ambassador", "duke"]})
        act(env, "p0", "income")
        act(env, "p1", "tax")
        backend = MockBackend(respond=lambda m: '{"action": 1}')
        agent = LLMAgent(backend=backend, spec=get_game("coup"))
        agent.act(
            observation=env.observe(player_id="p2"),
            interaction=env.current_interaction(),
            legal_actions=env.legal_actions(player_id="p2"),
        )
        prompts.append(json.dumps(backend.calls[0]))
    assert prompts[0] == prompts[1]


def test_openrouter_needs_a_key_from_the_environment(monkeypatch):
    from selfplay_worlds.inference import OpenRouterBackend

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is not set"):
        OpenRouterBackend(model="any/model")


def test_vllm_backend_points_at_a_local_server_by_default(monkeypatch):
    from selfplay_worlds.inference import VLLMBackend

    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    if importlib.util.find_spec("openai") is None:
        with pytest.raises(ImportError, match="uv sync --extra llm"):
            VLLMBackend(model="some-model")
    else:
        backend = VLLMBackend(model="some-model")  # constructing a client makes no network call
        assert backend.base_url == "http://localhost:8000/v1"
