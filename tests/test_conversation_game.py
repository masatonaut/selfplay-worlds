"""ConversationGame: ordering, talk, retries, fallbacks, forced moves, the record, save and resume."""

import json

import pytest
from helpers import new_game

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.core.scheduler import Scheduler
from selfplay_worlds.games.coup import CoupEnv, CoupHeuristicPolicy
from selfplay_worlds.policies import RandomPolicy, ReplayPolicy, ScriptedPolicy

HANDS = {"p0": ["captain", "assassin"], "p1": ["duke", "contessa"], "p2": ["ambassador", "duke"]}


class Recorder(ScriptedPolicy):
    """Plays queued answers, then the first option. Records every call."""

    def __init__(self, answers=(), messages=()):
        super().__init__(game_name="coup")
        self.answers, self.messages = list(answers), list(messages)
        self.calls, self.talk_calls = [], []

    def get_message(self, *, observation, conversation):
        self.talk_calls.append({"phase": observation["phase"], "conversation": list(conversation)})
        return self.messages.pop(0) if self.messages else None

    def step(self, *, observation, conversation):
        self.calls.append({"phase": observation["phase"], "feedback": observation.get("feedback")})
        return self.answers.pop(0) if self.answers else {"option": 1}


class EagerChallenger(ScriptedPolicy):
    """Challenges whenever it can, otherwise takes the first option."""

    def __init__(self):
        super().__init__(game_name="coup")

    def step(self, *, observation, conversation):
        if {"type": "challenge"} in observation["options"]:
            return {"type": "challenge"}
        return {"option": 1}


class ReverseScheduler(Scheduler):
    def order(self, *, phase):
        return list(reversed(phase.eligible))


def _fixed_env():
    return new_game(HANDS)


def _play(env, players, **kwargs):
    game = ConversationGame(env=env, players=players, **kwargs)
    game.run()
    return game


def _actions(game):
    return [e for e in game.record.entries if e["kind"] == "action"]


def _recorders():
    return {pid: Recorder() for pid in ("p0", "p1", "p2")}


# --------------------------------------------------------- who is asked when


def test_action_phase_asks_only_the_eligible_player():
    first = _actions(_play(_fixed_env(), _recorders()))[0]
    assert first["mode"] == "action"
    assert first["player_id"] == "p0"


def test_response_window_asks_in_environment_order_by_default():
    players = {"p0": ReplayPolicy(game_name="coup", answers=[{"type": "tax"}]), "p1": EagerChallenger(), "p2": EagerChallenger()}
    challenge = next(e for e in _actions(_play(_fixed_env(), players)) if e["content"] == {"type": "challenge"})
    assert challenge["mode"] == "response_window"
    assert challenge["player_id"] == "p1"


def test_scheduler_changes_who_challenges_first():
    """Same game, same policies: only the Scheduler differs."""
    players = {"p0": ReplayPolicy(game_name="coup", answers=[{"type": "tax"}]), "p1": EagerChallenger(), "p2": EagerChallenger()}
    game = _play(_fixed_env(), players, scheduler=ReverseScheduler())
    challenge = next(e for e in _actions(game) if e["content"] == {"type": "challenge"})
    assert challenge["player_id"] == "p2"


def test_players_who_already_passed_are_not_asked_again():
    players = _recorders()
    players["p0"].answers = [{"type": "tax"}]
    window = [e for e in _actions(_play(_fixed_env(), players)) if e["phase"] == "challenge_action"]
    assert [e["player_id"] for e in window[:2]] == ["p1", "p2"]
    assert window[0]["phase_id"] == window[1]["phase_id"]


def test_each_phase_is_recorded_once_with_its_eligible_players():
    game = _play(_fixed_env(), _recorders())
    phases = [e for e in game.record.entries if e["kind"] == "phase"]
    assert phases[0]["phase"] == "action" and phases[0]["eligible"] == ["p0"]
    assert len({e["phase_id"] for e in phases}) == len(phases)


# --------------------------------------------------------------------- talk


def test_talk_comes_before_the_action_and_stays_out_of_the_environment():
    players = _recorders()
    players["p0"].answers = [{"type": "tax"}]
    players["p0"].messages = ["Duke, obviously."]
    game = _play(_fixed_env(), players)
    entries = game.record.entries
    message = next(e for e in entries if e["kind"] == "message")
    assert message["player_id"] == "p0" and message["content"] == "Duke, obviously."
    assert entries[message["index"] + 1]["kind"] == "action"
    assert not any("says" in line for line in game.env.get_state()["history"])
    assert game.get_conversation(player_id="p1")[0]["content"] == "Duke, obviously."
    assert players["p1"].talk_calls[0]["conversation"][0]["content"] == "Duke, obviously."


def test_phases_without_talk_rounds_never_ask_for_talk():
    players = _recorders()
    players["p0"].answers = [{"type": "tax"}]
    players["p0"].messages = [None]
    players["p1"].answers = [{"type": "challenge"}]  # Alice is bluffing: she must reveal a card
    _play(_fixed_env(), players)
    assert players["p0"].calls[1]["phase"] == "lose_influence"
    assert "lose_influence" not in [c["phase"] for c in players["p0"].talk_calls]


def test_the_record_holds_only_the_table_and_policies_see_the_step():
    class StepSpy(Recorder):
        def step(self, *, observation, conversation):
            self.steps.append((observation["step"], self.env_steps()))
            return super().step(observation=observation, conversation=conversation)

    env = _fixed_env()
    players = {pid: StepSpy() for pid in ("p0", "p1", "p2")}
    for policy in players.values():
        policy.steps, policy.env_steps = [], lambda: env.n_steps
    players["p0"].messages = ["Duke, obviously."]
    game = _play(env, players)
    assert {e["kind"] for e in game.record.entries} <= {"phase", "message", "action", "event"}
    assert all(set(e) >= {"kind", "player_id", "content"} and "visibility" not in e for e in game.record.entries)
    assert [e["kind"] for e in game.get_conversation(player_id="p1")] == ["message"]
    seen = [s for policy in players.values() for s in policy.steps]
    assert seen and all(step == current for step, current in seen)  # observation["step"] == env.n_steps


# ----------------------------------------------------- invalid answers and fallbacks


def test_unreadable_answer_is_retried_with_the_reason():
    players = _recorders()
    players["p0"].answers = [{"type": "fly"}]
    game = _play(_fixed_env(), players)
    first, second = _actions(game)[:2]
    assert first["accepted"] is False and first["attempt"] == 1 and first["content"] is None
    assert first["error"].startswith("could not read the answer")
    assert second["accepted"] is True and second["attempt"] == 2
    assert players["p0"].calls[1]["feedback"] == first["error"]


def test_illegal_action_is_retried_with_the_environments_reason():
    players = _recorders()
    players["p0"].answers = [{"type": "coup", "target": "p1"}]  # only 2 coins
    game = _play(_fixed_env(), players)
    first = _actions(game)[0]
    assert first["accepted"] is False and first["content"] == {"type": "coup", "target": "p1"}
    assert "illegal action" in first["error"] and "legal actions are" in first["error"]
    assert players["p0"].calls[1]["feedback"] == first["error"]


def test_fallback_after_too_many_invalid_answers():
    class Hopeless(ScriptedPolicy):
        def step(self, *, observation, conversation):
            return {"type": "fly"}

    players = {"p0": Hopeless(game_name="coup"), "p1": Recorder(), "p2": Recorder()}
    first_turn = _actions(_play(_fixed_env(), players, max_retries=2))[:4]
    assert [e["accepted"] for e in first_turn] == [False, False, False, True]
    assert first_turn[3]["source"] == "fallback" and first_turn[3]["attempt"] == 4
    assert first_turn[3]["content"] == {"type": "income"}  # the first option


def test_forced_moves_do_not_call_the_policy():
    class MustNotBeAsked(ScriptedPolicy):
        def get_message(self, **kwargs):
            raise AssertionError("a forced move reached the policy")

        def step(self, **kwargs):
            raise AssertionError("a forced move reached the policy")

    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa"]}, coins={"p0": 7})
    players = {"p0": ReplayPolicy(game_name="coup", answers=[{"type": "coup", "target": "p1"}]), "p1": MustNotBeAsked(game_name="coup")}
    reveal = _actions(_play(env, players))[-1]
    assert reveal["phase"] == "lose_influence" and reveal["source"] == "forced"


def test_forced_moves_can_be_sent_to_the_policy():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa"]}, coins={"p0": 7})
    loser = Recorder()
    players = {"p0": ReplayPolicy(game_name="coup", answers=[{"type": "coup", "target": "p1"}]), "p1": loser}
    _play(env, players, skip_forced_moves=False)
    assert [c["phase"] for c in loser.calls] == ["lose_influence"]


# ---------------------------------------------------------------- guard rails


def test_players_must_match_the_seats():
    with pytest.raises(ValueError, match=r"missing \['p2'\]"):
        ConversationGame(env=_fixed_env(), players={"p0": Recorder(), "p1": Recorder()})


def test_max_attempts_stops_a_runaway_game():
    players = {pid: RandomPolicy(game_name="coup", seed=i) for i, pid in enumerate(("p0", "p1", "p2"))}
    with pytest.raises(RuntimeError, match="max_attempts"):
        _play(_fixed_env(), players, max_attempts=3)


# ------------------------------------------------------- record and determinism


def _heuristic_game(seed):
    env = CoupEnv(game_config={"num_players": 4, "seed": seed})
    game = _play(env, {f"p{i}": CoupHeuristicPolicy(seed=100 + i) for i in range(4)})
    return game.env.get_state(view="full"), game.record.entries


def test_same_seed_and_policies_give_an_identical_game():
    assert _heuristic_game(5) == _heuristic_game(5)


def test_different_seeds_give_different_games():
    assert len({json.dumps(_heuristic_game(seed)[1]) for seed in range(5)}) > 1


def test_record_is_ordered_json_and_starts_with_the_opening():
    game = _play(CoupEnv(game_config={"num_players": 3, "seed": 3}), {f"p{i}": CoupHeuristicPolicy(seed=i) for i in range(3)})
    entries = game.record.entries
    assert [e["index"] for e in entries] == list(range(len(entries)))
    assert entries[0]["kind"] == "event" and entries[0]["content"].startswith("Game starts with 3 players.")
    assert {e["kind"] for e in entries} <= {"phase", "message", "thinking", "action", "event"}
    json.dumps(entries)


def test_the_same_code_drives_two_different_games():
    from fixtures.talk_then_vote import TalkThenVoteEnv

    _play(_fixed_env(), _recorders())
    name = "talk_then_vote_fixture"
    vote = {pid: ReplayPolicy(game_name=name, answers=[{"type": "vote", "target": "p1"}]) for pid in ("p0", "p1", "p2")}
    vote["p1"] = ReplayPolicy(game_name=name, answers=[{"type": "vote", "target": "p2"}])
    final = _play(TalkThenVoteEnv(game_config={"rounds": 1}), vote).env.get_state()
    assert final["done"] and final["winners"] == ["p0", "p2"]


def test_policies_must_be_made_for_this_game():
    players = {**_recorders(), "p2": RandomPolicy(game_name="chess")}
    with pytest.raises(ValueError, match=r"\['p2'\] were made for another game"):
        ConversationGame(env=_fixed_env(), players=players)


# --------------------------------------------------------------- save and resume


def _heuristics(n):
    return {f"p{i}": CoupHeuristicPolicy(seed=10 + i) for i in range(n)}


def test_interrupted_and_resumed_game_matches_an_uninterrupted_one(tmp_path):
    config = {"num_players": 3, "seed": 3}
    complete = _play(CoupEnv(game_config=config), _heuristics(3))

    interrupted = ConversationGame(env=CoupEnv(game_config=config), players=_heuristics(3))
    for _ in range(9):
        interrupted.step()
    interrupted.save(folder=tmp_path / "run")

    meta = json.loads((tmp_path / "run" / "game.json").read_text(encoding="utf-8"))
    resumed = ConversationGame(env=CoupEnv(game_config=meta["game_config"]), players=_heuristics(3))
    resumed.load(folder=tmp_path / "run")
    resumed.run()
    assert resumed.record.entries == complete.record.entries
    assert resumed.env.get_state(view="full") == complete.env.get_state(view="full")


def test_resume_keeps_non_default_settings(tmp_path):
    """The old CheckpointStore lost max_turns on resume. game.json now carries every setting."""
    config = {"num_players": 3, "seed": 0, "max_turns": 2}
    game = ConversationGame(env=CoupEnv(game_config=config), players=_heuristics(3))
    game.step()
    game.save(folder=tmp_path / "run")

    meta = json.loads((tmp_path / "run" / "game.json").read_text(encoding="utf-8"))
    resumed = ConversationGame(env=CoupEnv(game_config=meta["game_config"]), players=_heuristics(3))
    resumed.load(folder=tmp_path / "run")
    assert resumed.run()["termination_reason"] == "turn_limit"


def test_run_can_save_after_every_step(tmp_path):
    game = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 1}), players=_heuristics(3))
    final = game.run(save_folder=tmp_path / "run")
    meta = json.loads((tmp_path / "run" / "game.json").read_text(encoding="utf-8"))
    assert final["done"] and meta["n_steps"] == game.env.n_steps
    assert sorted(meta["files"]) == ["env.pkl", "policies/p0.pkl", "policies/p1.pkl", "policies/p2.pkl", "record.json"]


def test_load_detects_a_save_that_was_interrupted_or_edited(tmp_path):
    game = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 1}), players=_heuristics(3))
    game.step()
    game.save(folder=tmp_path / "run")
    (tmp_path / "run" / "record.json").write_text('{"entries": []}', encoding="utf-8")
    fresh = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 1}), players=_heuristics(3))
    with pytest.raises(ValueError, match="does not match game.json"):
        fresh.load(folder=tmp_path / "run")


def test_load_refuses_other_settings_or_policy_classes(tmp_path):
    game = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 1}), players=_heuristics(3))
    game.save(folder=tmp_path / "run")
    other_seed = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 2}), players=_heuristics(3))
    with pytest.raises(ValueError, match="seed"):
        other_seed.load(folder=tmp_path / "run")
    other_policy = ConversationGame(
        env=CoupEnv(game_config={"num_players": 3, "seed": 1}),
        players={**_heuristics(3), "p1": RandomPolicy(game_name="coup")},
    )
    with pytest.raises(ValueError, match="p1 was saved as a CoupHeuristicPolicy"):
        other_policy.load(folder=tmp_path / "run")
