"""Policies: base behaviour, scripted policies, and the LLM Player on MockBackend only.

No network, no API key, no GPU.
"""

import importlib.util
import json

import pytest
from helpers import act, new_game

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.games.coup import CoupEnv
from selfplay_worlds.inference import MockBackend
from selfplay_worlds.inference.base import GenerationConfig
from selfplay_worlds.inference.usage import UsageLimitExceeded, UsageLimits, UsageTracker
from selfplay_worlds.policies import Player, RandomPolicy, ReplayPolicy

HANDS = {"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}
DECIDE_1 = '<thinking>Safe play.</thinking><answer>{"option": 1}</answer>'
SILENT = "<thinking>Nothing to add.</thinking><answer></answer>"


def replies(*, decide=DECIDE_1, talk=SILENT):
    """One reply for talk prompts, another for decisions."""
    return lambda messages: talk if "moment to talk" in messages[-1]["content"] else decide


def mock_model(*, decide=DECIDE_1, talk=SILENT):
    return MockBackend(respond=replies(decide=decide, talk=talk))


def _player(model=None, **kwargs):
    return Player(game_name="coup", model=model or mock_model(), **kwargs)


# ------------------------------------------------------------------ base policy


def test_a_policy_needs_a_game_name():
    with pytest.raises(ValueError, match="name of the game"):
        RandomPolicy(game_name="")


def test_unknown_games_render_observations_as_json():
    rendered = RandomPolicy(game_name="unregistered").render_observation(observation={"b": 1, "a": [2]})
    assert json.loads(rendered) == {"a": [2], "b": 1}


def test_random_policy_is_seeded_and_survives_save_and_load(tmp_path):
    observation = {"options": [{}] * 6}
    a, b = RandomPolicy(game_name="coup", seed=3), RandomPolicy(game_name="coup", seed=3)
    assert [a.get_action(observation=observation, conversation=[]) for _ in range(5)] == [
        b.get_action(observation=observation, conversation=[]) for _ in range(5)
    ]
    path = a.save(path=tmp_path / "a.pkl")
    restored = RandomPolicy(game_name="coup", seed=999)
    restored.load(path=path)
    assert restored.get_action(observation=observation, conversation=[]) == a.get_action(observation=observation, conversation=[])


def test_policy_load_refuses_another_class_or_game(tmp_path):
    path = RandomPolicy(game_name="coup").save(path=tmp_path / "p.pkl")
    with pytest.raises(TypeError, match="RandomPolicy"):
        ReplayPolicy(game_name="coup").load(path=path)
    with pytest.raises(ValueError, match="saved for game 'coup'"):
        RandomPolicy(game_name="chess").load(path=path)


def test_replay_policy_plays_its_script_then_its_fallback():
    policy = ReplayPolicy(game_name="coup", answers=[{"type": "tax"}], messages=["Duke."])
    assert policy.get_message(observation={}, conversation=[]) == "Duke."
    assert policy.get_action(observation={}, conversation=[]) == {"type": "tax"}
    assert policy.get_message(observation={}, conversation=[]) is None
    assert policy.get_action(observation={}, conversation=[]) == {"option": 1}


# ---------------------------------------------------------------- Player parsing


@pytest.mark.parametrize(
    "text, expected",
    [
        ('<thinking>I bluff.</thinking><answer>{"option": 2}</answer>', {"thinking": "I bluff.", "answer": '{"option": 2}'}),
        ("<THINKING> a </THINKING>\n<Answer> 3 </Answer>", {"thinking": "a", "answer": "3"}),
        ('{"option": 1}', {"thinking": None, "answer": '{"option": 1}'}),
        ("<thinking>only thoughts</thinking>", {"thinking": "only thoughts", "answer": None}),
        ("<thinking></thinking><answer></answer>", {"thinking": None, "answer": None}),
    ],
)
def test_parse_response(text, expected):
    assert _player().parse_response(text=text) == expected


@pytest.mark.parametrize(
    "answer, expected",
    [
        ('{"option": 2}', {"option": 2}),
        ('{"option": "3"}', {"option": 3}),
        ('```json\n{"option": 1}\n```', {"option": 1}),
        ("I pick 4. {\"option\": 4} done", {"option": 4}),
        ("2", {"option": 2}),
        ('{"type": "steal", "target": "p1"}', {"type": "steal", "target": "p1"}),
        ("I take income.", {}),
        (None, {}),
    ],
)
def test_parse_answer(answer, expected):
    assert _player().parse_answer(answer=answer, observation={}) == expected


# ---------------------------------------------------------------- Player prompts


def test_decision_prompt_has_rules_situation_and_numbered_options():
    model = mock_model()
    env = new_game(HANDS)
    answer = _player(model).get_action(observation=env.get_observation(player_id="p0"), conversation=[])
    assert answer == {"option": 1}
    system, user = model.calls[0][0]["content"], model.calls[0][1]["content"]
    assert "You are playing Coup" in system and "<thinking>" in system
    assert "Your hidden cards: duke, captain." in user
    assert '1. {"type": "income"}' in user
    assert '<answer>{"option": <number>}</answer>' in user


def test_talk_prompt_shows_the_conversation_and_silence_is_none():
    model = mock_model(talk="<answer>I have the Duke.</answer>")
    player = _player(model)
    env = new_game(HANDS)
    conversation = [{"kind": "message", "player_id": "p1", "content": "Careful, Alice."}]
    assert player.get_message(observation=env.get_observation(player_id="p0"), conversation=conversation) == "I have the Duke."
    assert "- p1 says: Careful, Alice." in model.calls[0][1]["content"]
    assert _player(mock_model(talk="<answer>null</answer>")).get_message(
        observation=env.get_observation(player_id="p0"), conversation=[]
    ) is None


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
        model = mock_model()
        _player(model).get_action(observation=env.get_observation(player_id="p2"), conversation=[])
        prompts.append(json.dumps(model.calls[0]))
    assert prompts[0] == prompts[1]


# --------------------------------------------------------------- Player in a game


def _llm_game(models, seed=1, **config):
    env = CoupEnv(game_config={"num_players": 3, "seed": seed, **config})
    return ConversationGame(env=env, players={pid: _player(models[pid]) for pid in env.player_ids})


def test_full_game_with_players_on_a_mock_backend():
    game = _llm_game({pid: mock_model() for pid in ("p0", "p1", "p2")})
    final = game.run()
    assert final["done"] and len(final["winners"]) == 1
    thinking = [e for e in game.record.entries if e["kind"] == "thinking"]
    assert thinking and all(e["visibility"] == "private" for e in thinking)
    assert game.players["p0"].usage.model_calls == len(game.players["p0"].transcript) > 0


def test_unreadable_reply_is_retried_with_an_explanation():
    # Alice starts: her first two calls are the talk prompt and then the decision.
    model = MockBackend(replies=[SILENT, "I take income."], respond=replies())
    game = _llm_game({"p0": model, "p1": mock_model(), "p2": mock_model()}, seed=0, starting_player="p0")
    game.run()
    first_p0 = [e for e in game.record.entries if e["kind"] == "action" and e["player_id"] == "p0"][:2]
    assert first_p0[0]["accepted"] is False
    assert first_p0[0]["error"] == "could not read the answer: no answer could be read from the reply"
    assert first_p0[1]["accepted"] is True and first_p0[1]["attempt"] == 2
    retry_prompt = next(c for c in model.calls if "previous answer was rejected" in c[1]["content"])[1]["content"]
    assert "Your previous answer was rejected: could not read the answer: no answer could be read from the reply" in retry_prompt


def test_player_saves_without_its_model_and_needs_set_model(tmp_path):
    player = _player()
    env = new_game(HANDS)
    player.get_action(observation=env.get_observation(player_id="p0"), conversation=[])
    path = player.save(path=tmp_path / "player.pkl")  # the mock holds a lambda, which cannot be pickled

    restored = Player(game_name="coup", model=None)
    restored.load(path=path)
    assert restored.model is None
    assert restored.transcript == player.transcript and restored.usage.model_calls == 1
    assert restored.describe()["backend"] == "mock"
    with pytest.raises(RuntimeError, match="set_model"):
        restored.get_action(observation=env.get_observation(player_id="p0"), conversation=[])
    restored.set_model(model=mock_model())
    assert restored.get_action(observation=env.get_observation(player_id="p0"), conversation=[]) == {"option": 1}


def test_player_budget_stops_before_the_next_call():
    player = _player(usage_limits=UsageLimits(max_calls=1))
    observation = new_game(HANDS).get_observation(player_id="p0")
    player.get_action(observation=observation, conversation=[])
    with pytest.raises(UsageLimitExceeded):
        player.get_action(observation=observation, conversation=[])


def test_generation_settings_reach_the_model():
    seen = {}

    class Spy(MockBackend):
        def generate(self, **kwargs):
            seen.update(kwargs)
            return super().generate(**kwargs)

    player = _player(Spy(respond=lambda m: DECIDE_1), generation_config=GenerationConfig(max_tokens=50, temperature=1.0, top_p=0.9, top_k=40))
    player.get_action(observation=new_game(HANDS).get_observation(player_id="p0"), conversation=[])
    assert (seen["max_tokens"], seen["temperature"], seen["top_p"], seen["top_k"]) == (50, 1.0, 0.9, 40)


# ------------------------------------------------------------- usage and backends


def test_usage_aggregation_and_budget():
    usage = UsageTracker(limits=UsageLimits(max_calls=2))
    usage.record({"model": "m", "input_tokens": 10, "output_tokens": 4, "latency_s": 0.25})
    usage.record({"model": "m", "input_tokens": 7, "output_tokens": 3, "latency_s": 0.5})
    assert usage.state_dict()["model_calls"] == 2
    assert usage.total_input_tokens == 17 and usage.total_output_tokens == 7
    assert usage.cost_usd is None
    with pytest.raises(UsageLimitExceeded):
        usage.check_before_call()


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
