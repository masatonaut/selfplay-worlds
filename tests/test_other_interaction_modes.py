"""DISCUSSION and SIMULTANEOUS, exercised with a TEST FIXTURE (tests/fixtures).

Coup only needs SINGLE and RESPONSE_WINDOW. These tests show the same Runner
also handles open discussion and simultaneous moves. They do not mean a real
game with these modes exists yet (see docs/roadmap.md, Milestone 2).
"""

from fixtures.talk_then_vote import TalkThenVoteEnv

from selfplay_worlds.agents.base import Agent
from selfplay_worlds.core.interaction import InteractionMode
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.core.scheduler import Scheduler
from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.episodes.log import EpisodeLogger


class Talker(Agent):
    """Speaks in the discussion and votes for a fixed player."""

    def __init__(self, name, vote_for, env=None):
        super().__init__()
        self.name, self.vote_for, self.env = name, vote_for, env
        self.vote_calls = []

    def act(self, *, observation, interaction, legal_actions, feedback=None):
        if interaction.mode is InteractionMode.DISCUSSION:
            return AgentOutput(message=f"I am {self.name}. I have heard {len(observation['history'])} messages.")
        if feedback is None and self.env is not None:
            # SIMULTANEOUS: no vote may have reached the environment yet.
            self.vote_calls.append(len(self.env.full_state()["votes"]))
        return AgentOutput(action={"type": "vote", "target": self.vote_for})


def _play(env, agents, **runner_kwargs):
    steps = []
    logger = EpisodeLogger()
    result = Runner(on_event=steps.append, **runner_kwargs).run(env=env, agents=agents, seed=0, logger=logger)
    return result, [s for s in steps if s["kind"] == "step"], logger.record


def test_discussion_repeats_the_order_until_the_environment_closes_it():
    env = TalkThenVoteEnv(rounds=2)
    agents = {"p0": Talker("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p1")}
    _, steps, _ = _play(env, agents)
    talk = [s for s in steps if s["interaction"]["mode"] == "discussion"]
    assert [s["actor"] for s in talk] == ["p0", "p1", "p2", "p0", "p1", "p2"]
    assert len({s["interaction"]["id"] for s in talk}) == 1  # one open discussion
    assert all(s["output"]["action"] is None for s in talk)  # message only


def test_who_speaks_when_is_a_runner_decision():
    class P2First(Scheduler):
        def order(self, *, interaction):
            return ["p2", "p0", "p1"]

    env = TalkThenVoteEnv(rounds=1)
    agents = {"p0": Talker("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p1")}
    _, steps, _ = _play(env, agents, scheduler=P2First())
    talk = [s["actor"] for s in steps if s["interaction"]["mode"] == "discussion"]
    assert talk == ["p2", "p0", "p1"]


def test_discussion_requires_a_message():
    class Silent(Agent):
        def act(self, *, observation, interaction, legal_actions, feedback=None):
            if interaction.mode is InteractionMode.DISCUSSION:
                return AgentOutput(action={"type": "speak"})  # no words
            return AgentOutput(action=legal_actions[0])

    env = TalkThenVoteEnv(rounds=1)
    agents = {"p0": Silent(), "p1": Talker("p1", "p0"), "p2": Talker("p2", "p0")}
    _, steps, _ = _play(env, agents, max_retries=1)
    p0_talk = [s for s in steps if s["actor"] == "p0" and s["interaction"]["mode"] == "discussion"]
    assert [s["accepted"] for s in p0_talk] == [False, False, True]
    assert p0_talk[0]["error"] == "a message is required during the discussion"
    assert p0_talk[-1]["fallback"] is True
    assert p0_talk[-1]["output"]["message"] == "(no valid response)"


def test_simultaneous_vote_asks_everyone_before_any_vote_is_applied():
    env = TalkThenVoteEnv(rounds=0)
    agents = {pid: Talker(pid, target, env=env) for pid, target in (("p0", "p1"), ("p1", "p2"), ("p2", "p1"))}
    result, steps, _ = _play(env, agents)
    assert [agents[p].vote_calls for p in ("p0", "p1", "p2")] == [[0], [0], [0]]
    votes = [s for s in steps if s["interaction"]["mode"] == "simultaneous"]
    assert len({s["interaction"]["id"] for s in votes}) == 1
    assert result.winners == ["p0", "p2"]
    assert env.public_history()[-1] == "p1 is voted out."


def test_votes_stay_secret_until_everyone_has_voted():
    env = TalkThenVoteEnv(rounds=0)
    agents = {pid: Talker(pid, target) for pid, target in (("p0", "p1"), ("p1", "p2"), ("p2", "p1"))}
    _, _, record = _play(env, agents)
    log = record["public_log"]
    assert log[:3] == ["p0 has voted.", "p1 has voted.", "p2 has voted."]
    assert log[3] == "Votes: p0 -> p1, p1 -> p2, p2 -> p1."


def test_messages_are_rejected_during_the_vote():
    class Chatty(Talker):
        def act(self, *, observation, interaction, legal_actions, feedback=None):
            output = super().act(observation=observation, interaction=interaction, legal_actions=legal_actions, feedback=feedback)
            if interaction.mode is InteractionMode.SIMULTANEOUS and feedback is None:
                output.message = "Vote with me!"
            return output

    env = TalkThenVoteEnv(rounds=0)
    agents = {"p0": Chatty("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p1")}
    _, steps, _ = _play(env, agents)
    p0 = [s for s in steps if s["actor"] == "p0"]
    assert p0[0]["accepted"] is False and "no messages" in p0[0]["error"]
    assert p0[1]["accepted"] is True  # the retry dropped the message


def test_tied_vote():
    env = TalkThenVoteEnv(rounds=0)
    agents = {"p0": Talker("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p0")}
    result, _, _ = _play(env, agents)
    assert result.winners == ["p0", "p1", "p2"]
