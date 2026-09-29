"""The Runner: ordering, retries, fallbacks, forced moves, determinism."""

import pytest

from selfplay_worlds.agents.base import Agent
from selfplay_worlds.agents.scripted import RandomAgent, ScriptedAgent
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.core.scheduler import Scheduler
from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.episodes.log import EpisodeLogger
from selfplay_worlds.games import get_game

HANDS = {"p0": ["captain", "assassin"], "p1": ["duke", "contessa"], "p2": ["ambassador", "duke"]}


def eager_challenger(*, observation, interaction, legal_actions, rng):
    """Challenges whenever it can, otherwise takes the first legal action."""
    for action in legal_actions:
        if action.type.value == "challenge":
            return AgentOutput(action=action)
    return AgentOutput(action=legal_actions[0])


class ReverseScheduler(Scheduler):
    def order(self, *, interaction):
        return list(reversed(interaction.eligible_players))


def _run(env, agents, **runner_kwargs):
    events = []
    logger = EpisodeLogger()
    Runner(on_event=events.append, **runner_kwargs).run(env=env, agents=agents, seed=0, logger=logger)
    return [e for e in events if e["kind"] == "step"], logger.record


def _fixed_env():
    return get_game("coup").make_env(num_players=3, initial_hands=HANDS, starting_player="p0")


class Recorder(Agent):
    """Returns queued outputs, then the first legal action. Records every call."""

    def __init__(self, outputs=()):
        super().__init__()
        self.outputs = list(outputs)
        self.calls = []

    def act(self, *, observation, interaction, legal_actions, feedback=None):
        self.calls.append({"phase": interaction.phase, "feedback": feedback, "legal": legal_actions})
        if self.outputs:
            return self.outputs.pop(0)
        return AgentOutput(action=legal_actions[0])


# --------------------------------------------------------- who is asked when


def test_single_interaction_asks_only_the_eligible_player():
    agents = {pid: Recorder() for pid in ("p0", "p1", "p2")}
    steps, _ = _run(_fixed_env(), agents)
    first = steps[0]
    assert first["interaction"]["mode"] == "single"
    assert first["interaction"]["eligible_players"] == ["p0"]
    assert first["actor"] == "p0"


def test_response_window_asks_in_environment_order_by_default():
    agents = {
        "p0": ScriptedAgent(script=[AgentOutput(action={"type": "tax"})]),  # a bluff
        "p1": ScriptedAgent(policy=eager_challenger),
        "p2": ScriptedAgent(policy=eager_challenger),
    }
    steps, _ = _run(_fixed_env(), agents)
    challenge = next(s for s in steps if s["output"]["action"] == {"type": "challenge"})
    assert challenge["interaction"]["mode"] == "response_window"
    assert challenge["actor"] == "p1"


def test_scheduler_changes_who_challenges_first():
    """Same game, same agents: only the Scheduler differs."""
    agents = {
        "p0": ScriptedAgent(script=[AgentOutput(action={"type": "tax"})]),
        "p1": ScriptedAgent(policy=eager_challenger),
        "p2": ScriptedAgent(policy=eager_challenger),
    }
    steps, record = _run(_fixed_env(), agents, scheduler=ReverseScheduler())
    challenge = next(s for s in steps if s["output"]["action"] == {"type": "challenge"})
    assert challenge["actor"] == "p2"
    assert record["config"]["runner"]["scheduler"] == "ReverseScheduler"


def test_players_who_already_passed_are_not_asked_again():
    agents = {pid: Recorder() for pid in ("p0", "p1", "p2")}
    agents["p0"].outputs = [AgentOutput(action={"type": "tax"})]
    steps, _ = _run(_fixed_env(), agents)
    window = [s for s in steps if s["interaction"]["phase"] == "challenge_action"]
    assert [s["actor"] for s in window[:2]] == ["p1", "p2"]
    assert window[0]["interaction"]["id"] == window[1]["interaction"]["id"]


# --------------------------------------------------- invalid outputs and fallbacks


def test_invalid_output_is_retried_with_the_environments_feedback():
    agents = {pid: Recorder() for pid in ("p0", "p1", "p2")}
    agents["p0"].outputs = [AgentOutput(action={"type": "fly"})]
    steps, record = _run(_fixed_env(), agents)
    assert steps[0]["accepted"] is False and steps[0]["attempt"] == 1
    assert steps[1]["accepted"] is True and steps[1]["attempt"] == 2
    assert agents["p0"].calls[1]["feedback"] == steps[0]["error"]
    assert "illegal action" in steps[0]["error"]
    assert record["result"]["num_invalid_outputs"] == 1
    assert agents["p0"].state.attempted_actions[:2] == [{"type": "fly"}, {"type": "income"}]
    assert agents["p0"].state.accepted_actions[0] == {"type": "income"}


def test_fallback_after_too_many_invalid_outputs():
    class Hopeless(Agent):
        def act(self, *, observation, interaction, legal_actions, feedback=None):
            return AgentOutput(action={"type": "fly"}, message="I refuse.")

    agents = {"p0": Hopeless(), "p1": Recorder(), "p2": Recorder()}
    steps, _ = _run(_fixed_env(), agents, max_retries=2)
    first_turn = steps[:4]
    assert [s["accepted"] for s in first_turn] == [False, False, False, True]
    assert first_turn[3]["fallback"] is True
    assert first_turn[3]["attempt"] == 4
    assert first_turn[3]["output"]["action"] == {"type": "income"}  # legal_actions[0]
    assert first_turn[3]["output"]["metadata"]["reason"].startswith("illegal action")


def test_forced_moves_do_not_call_the_agent():
    class MustNotBeAsked(Agent):
        def act(self, **kwargs):
            raise AssertionError("a forced move reached the agent")

    env = get_game("coup").make_env(
        num_players=2, initial_hands={"p0": ["duke", "captain"], "p1": ["contessa"]}, initial_coins={"p0": 7}, starting_player="p0"
    )
    agents = {"p0": ScriptedAgent(script=[AgentOutput(action={"type": "coup", "target": "p1"})]), "p1": MustNotBeAsked()}
    steps, record = _run(env, agents)
    reveal = steps[-1]
    assert reveal["interaction"]["phase"] == "lose_influence"
    assert reveal["auto"] is True
    assert record["result"]["num_agent_calls"] == 1


def test_forced_moves_can_be_sent_to_the_agent():
    env = get_game("coup").make_env(
        num_players=2, initial_hands={"p0": ["duke", "captain"], "p1": ["contessa"]}, initial_coins={"p0": 7}, starting_player="p0"
    )
    loser = Recorder()
    agents = {"p0": ScriptedAgent(script=[AgentOutput(action={"type": "coup", "target": "p1"})]), "p1": loser}
    _run(env, agents, skip_forced_moves=False)
    assert [c["phase"] for c in loser.calls] == ["lose_influence"]


# ---------------------------------------------------------------- guard rails


def test_missing_agent_is_an_error():
    with pytest.raises(ValueError, match="no agent"):
        Runner().run(env=_fixed_env(), agents={"p0": Recorder(), "p1": Recorder()})


def test_max_steps_stops_a_runaway_episode():
    agents = {pid: RandomAgent(seed=i) for i, pid in enumerate(("p0", "p1", "p2"))}
    with pytest.raises(RuntimeError, match="max_steps"):
        Runner(max_steps=3).run(env=_fixed_env(), agents=agents, seed=0)


# ---------------------------------------------------------------- determinism


def _heuristic_game(seed: int):
    spec = get_game("coup")
    agents = {f"p{i}": ScriptedAgent(policy=spec.scripted_policy, seed=100 + i) for i in range(4)}
    logger = EpisodeLogger(include_full_state=True)
    result = Runner().run(env=spec.make_env(num_players=4), agents=agents, seed=seed, logger=logger)
    record = dict(logger.record)
    record.pop("created_at")
    return result, record


def test_same_seed_and_agents_give_an_identical_episode():
    (result_a, record_a), (result_b, record_b) = _heuristic_game(5), _heuristic_game(5)
    assert result_a == result_b
    assert record_a == record_b


def test_different_seeds_give_different_episodes():
    logs = {tuple(_heuristic_game(seed)[1]["public_log"]) for seed in range(5)}
    assert len(logs) > 1


def test_runner_contains_no_game_rules():
    """The same Runner object can drive two different games one after another."""
    from fixtures.talk_then_vote import TalkThenVoteEnv

    runner = Runner()
    coup_agents = {pid: Recorder() for pid in ("p0", "p1", "p2")}
    runner.run(env=_fixed_env(), agents=coup_agents, seed=0)
    vote_agents = {pid: Recorder() for pid in ("p0", "p1", "p2")}
    result = runner.run(env=TalkThenVoteEnv(rounds=1), agents=vote_agents, seed=0)
    assert result.termination_reason == "vote_finished"
