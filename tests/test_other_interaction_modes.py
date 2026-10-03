"""DISCUSSION and SIMULTANEOUS, exercised with a TEST FIXTURE (tests/fixtures).

Coup only needs ACTION and RESPONSE_WINDOW. These tests show the same
ConversationGame also handles open discussion and simultaneous moves. They do
not mean a real game with these modes exists yet (see docs/roadmap.md, Milestone 2).
"""

import json

from fixtures.talk_then_vote import TalkThenVoteEnv

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.core.scheduler import Scheduler
from selfplay_worlds.policies import ScriptedPolicy

GAME = "talk_then_vote_fixture"


class Talker(ScriptedPolicy):
    """Talks in the discussion and votes for a fixed player."""

    def __init__(self, name, vote_for, env=None):
        super().__init__(game_name=GAME)
        self.name, self.vote_for, self.env = name, vote_for, env
        self.vote_calls, self.talk_phases = [], []

    def get_message(self, *, observation, conversation):
        self.talk_phases.append(observation["phase"])
        return f"I am {self.name}. I have heard {len(conversation)} messages."

    def step(self, *, observation, conversation):
        if "feedback" not in observation and self.env is not None:
            # SIMULTANEOUS: no vote may have reached the environment yet.
            self.vote_calls.append(len(self.env.get_state(view="full")["votes"]))
        return {"type": "vote", "target": self.vote_for}


def _talkers(env=None, targets=(("p0", "p1"), ("p1", "p2"), ("p2", "p1"))):
    return {pid: Talker(pid, target, env=env) for pid, target in targets}


def _play(env, players, **kwargs):
    game = ConversationGame(env=env, players=players, **kwargs)
    final = game.run()
    return final, game


def _kind(game, kind):
    return [e for e in game.record.entries if e["kind"] == kind]


def test_discussion_runs_every_talk_round_in_order_then_closes():
    _, game = _play(TalkThenVoteEnv(game_config={"rounds": 2}), _talkers())
    talk = [e for e in _kind(game, "message") if e["mode"] == "discussion"]
    assert [e["player_id"] for e in talk] == ["p0", "p1", "p2", "p0", "p1", "p2"]
    assert len({e["phase_id"] for e in talk}) == 1  # one open discussion
    assert talk[-1]["content"] == "I am p2. I have heard 5 messages."  # everyone hears what came before
    done = [e for e in _kind(game, "action") if e["mode"] == "discussion"]
    assert all(e["source"] == "forced" and e["content"] == {"type": "done"} for e in done)


def test_who_speaks_when_is_a_scheduling_decision():
    class P2First(Scheduler):
        def order(self, *, phase):
            return ["p2", "p0", "p1"]

    _, game = _play(TalkThenVoteEnv(game_config={"rounds": 1}), _talkers(), scheduler=P2First())
    assert [e["player_id"] for e in _kind(game, "message")] == ["p2", "p0", "p1"]


def test_simultaneous_vote_asks_everyone_before_any_vote_is_applied():
    env = TalkThenVoteEnv(game_config={"rounds": 0})
    players = _talkers(env=env)
    final, game = _play(env, players)
    assert [players[p].vote_calls for p in ("p0", "p1", "p2")] == [[0], [0], [0]]
    votes = [e for e in _kind(game, "action") if e["mode"] == "simultaneous"]
    assert len({e["phase_id"] for e in votes}) == 1
    assert final["winners"] == ["p0", "p2"]
    assert final["history"][-1] == "p1 is voted out."


def test_votes_stay_secret_until_everyone_has_voted():
    final, _ = _play(TalkThenVoteEnv(game_config={"rounds": 0}), _talkers())
    assert final["history"][:3] == ["p0 has voted.", "p1 has voted.", "p2 has voted."]
    assert final["history"][3] == "Votes: p0 -> p1, p1 -> p2, p2 -> p1."


def test_nobody_is_asked_to_talk_during_the_vote():
    players = _talkers()
    _play(TalkThenVoteEnv(game_config={"rounds": 1}), players)
    assert all(p.talk_phases == ["discussion"] for p in players.values())


def test_a_rejected_simultaneous_answer_is_retried_with_typed_actions():
    """Regression for the old Runner, which turned typed actions into dicts on retry."""

    class SecondTry(Talker):
        def step(self, *, observation, conversation):
            if "feedback" not in observation:
                return {"type": "vote", "target": self.name}  # voting for yourself is illegal
            self.retry_observation = observation
            return super().step(observation=observation, conversation=conversation)

    env = TalkThenVoteEnv(game_config={"rounds": 0})
    players = {**_talkers(), "p0": SecondTry("p0", "p1")}
    final, game = _play(env, players)
    first, retry = [e for e in _kind(game, "action") if e["player_id"] == "p0"]
    assert first["accepted"] is False and "illegal action" in first["error"]
    assert retry["accepted"] is True and retry["source"] == "policy"
    assert players["p0"].retry_observation["votes_cast"] == 0  # still the pre-vote view
    assert final["winners"] == ["p0", "p2"]


def test_tied_vote():
    final, _ = _play(TalkThenVoteEnv(game_config={"rounds": 0}), _talkers(targets=(("p0", "p1"), ("p1", "p2"), ("p2", "p0"))))
    assert final["winners"] == ["p0", "p1", "p2"]


def test_resume_between_discussion_and_vote(tmp_path):
    full_final, full_game = _play(TalkThenVoteEnv(game_config={"rounds": 1}), _talkers())

    game = ConversationGame(env=TalkThenVoteEnv(game_config={"rounds": 1}), players=_talkers())
    game.step()  # the whole discussion
    assert game.env.get_dialogue_phase().phase == "vote"
    game.save(folder=tmp_path / "run")

    resumed = ConversationGame(env=TalkThenVoteEnv(game_config={"rounds": 1}), players=_talkers())
    resumed.load(folder=tmp_path / "run")
    assert resumed.run() == full_final
    assert json.dumps(resumed.record.entries) == json.dumps(full_game.record.entries)
