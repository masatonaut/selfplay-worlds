"""Focused tests for typed state, agent memory, checkpoints, and usage."""

import json

import pytest

from selfplay_worlds.agents.scripted import ScriptedAgent
from selfplay_worlds.agents.state import AgentState
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.core.scheduler import Scheduler
from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.episodes.checkpoint import CheckpointStore
from selfplay_worlds.episodes.log import EpisodeRecorder
from selfplay_worlds.games import get_game
from selfplay_worlds.games.coup import CoupAction, CoupActionType, CoupEnv, CoupPhase, CoupState
from selfplay_worlds.inference.usage import UsageLimitExceeded, UsageLimits, UsageTracker


def _agents(seed=10):
    spec = get_game("coup")
    return {
        f"p{i}": ScriptedAgent(policy=spec.scripted_policy, seed=seed + i)
        for i in range(3)
    }


def test_coup_action_serialization_and_structure_are_explicit():
    action = CoupAction(CoupActionType.STEAL, target="p1")
    assert CoupAction.from_dict(action.to_dict()) == action
    assert json.loads(json.dumps(action.to_dict())) == {"type": "steal", "target": "p1"}
    with pytest.raises(ValueError, match="fields must be"):
        CoupAction.from_dict({"type": "tax", "target": "p1"})


def test_coup_phase_and_legality_are_distinct():
    env = CoupEnv(num_players=3, starting_player="p0")
    env.reset(seed=0)
    assert env.state.phase is CoupPhase.ACTION
    typed, error = env.validate_action(player_id="p0", action={"type": "income"})
    assert typed == CoupAction(CoupActionType.INCOME) and error is None
    typed, error = env.validate_action(player_id="p0", action={"type": "coup", "target": "p1"})
    assert typed is None and error.startswith("illegal action")


def test_agent_state_round_trip_contains_experience_not_backend():
    state = AgentState(
        observations=[{"you": "p0"}],
        produced_messages=["Duke here."],
        attempted_actions=[{"type": "tax"}],
        accepted_actions=[{"type": "tax"}],
        validation_feedback=[None],
    )
    restored = AgentState.from_dict(json.loads(json.dumps(state.to_dict())))
    assert restored == state
    assert "backend" not in restored.to_dict()
    assert "implementation" not in restored.to_dict()


def test_coup_state_round_trip_preserves_rng_and_next_transition():
    env = CoupEnv(num_players=3, starting_player="p0")
    env.reset(seed=7)
    snapshot = json.loads(json.dumps(env.state_dict()))
    restored = CoupEnv(num_players=3, starting_player="p0")
    restored.load_state_dict(snapshot)
    assert isinstance(restored.state, CoupState)
    assert restored.full_state() == env.full_state()
    action = env.legal_actions(player_id="p0")[0]
    assert restored.step(player_id="p0", output=AgentOutput(action=action)).accepted
    assert env.step(player_id="p0", output=AgentOutput(action=action)).accepted
    assert restored.state_dict() == env.state_dict()


def test_interrupted_resume_matches_uninterrupted_trajectory(tmp_path):
    spec = get_game("coup")
    complete_env = spec.make_env(num_players=3)
    complete_log = EpisodeRecorder()
    complete_result = Runner().run(env=complete_env, agents=_agents(), seed=3, logger=complete_log)

    checkpoint = CheckpointStore(path=tmp_path / "coup.checkpoint.json")
    interrupted_env = spec.make_env(num_players=3)
    interrupted_log = EpisodeRecorder()
    accepted = 0

    def stop_after_seven(event):
        nonlocal accepted
        if event.get("accepted"):
            accepted += 1
        if accepted == 7:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Runner(on_event=stop_after_seven).run(
            env=interrupted_env,
            agents=_agents(),
            seed=3,
            logger=interrupted_log,
            checkpoint_store=checkpoint,
        )

    resumed_env = spec.make_env(num_players=3)
    resumed_log = EpisodeRecorder()
    resumed_result = Runner().run(
        env=resumed_env,
        agents=_agents(),
        seed=999,
        logger=resumed_log,
        checkpoint_store=checkpoint,
        resume=True,
    )
    assert resumed_result == complete_result
    assert resumed_env.public_history() == complete_env.public_history()
    assert resumed_log.record["events"] == complete_log.record["events"]


def test_resume_preserves_recorder_full_state_setting(tmp_path):
    spec = get_game("coup")
    checkpoint = CheckpointStore(path=tmp_path / "coup.checkpoint.json")

    def stop_after_first(event):
        if event.get("accepted"):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Runner(on_event=stop_after_first).run(
            env=spec.make_env(num_players=3),
            agents=_agents(),
            seed=3,
            logger=EpisodeRecorder(include_full_state=True),
            checkpoint_store=checkpoint,
        )

    resumed_log = EpisodeRecorder(include_full_state=False)
    Runner().run(
        env=spec.make_env(num_players=3),
        agents=_agents(),
        logger=resumed_log,
        checkpoint_store=checkpoint,
        resume=True,
    )
    assert resumed_log.include_full_state is True
    assert all("full_state_after" in event for event in resumed_log.record["events"])


def test_usage_aggregation_and_budget():
    usage = UsageTracker(limits=UsageLimits(max_calls=2))
    usage.record({"model": "m", "input_tokens": 10, "output_tokens": 4, "latency_s": 0.25})
    usage.record({"model": "m", "input_tokens": 7, "output_tokens": 3, "latency_s": 0.5})
    assert usage.state_dict()["model_calls"] == 2
    assert usage.total_input_tokens == 17
    assert usage.total_output_tokens == 7
    assert usage.cost_usd is None
    with pytest.raises(UsageLimitExceeded):
        usage.check_before_call()
    usage.reset()
    assert usage.model_calls == 0
    assert usage.limits == UsageLimits(max_calls=2)


class StartsWithP2(Scheduler):
    def order(self, *, interaction):
        players = list(interaction.eligible_players)
        return players[2:] + players[:2]


def test_scheduler_can_change_first_discussion_speaker():
    from fixtures.talk_then_vote import TalkThenVoteEnv
    from test_other_interaction_modes import Talker

    steps = []
    agents = {"p0": Talker("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p1")}
    Runner(scheduler=StartsWithP2(), on_event=steps.append).run(
        env=TalkThenVoteEnv(rounds=1), agents=agents, seed=0
    )
    discussion = [event for event in steps if event.get("interaction", {}).get("phase") == "discussion"]
    assert discussion[0]["actor"] == "p2"


def test_simultaneous_pending_outputs_survive_checkpoint_resume(tmp_path):
    from fixtures.talk_then_vote import TalkThenVoteEnv
    from test_other_interaction_modes import Talker

    def talkers():
        return {"p0": Talker("p0", "p1"), "p1": Talker("p1", "p2"), "p2": Talker("p2", "p1")}

    full_env = TalkThenVoteEnv(rounds=0)
    full_result = Runner().run(env=full_env, agents=talkers(), seed=0)
    checkpoint = CheckpointStore(path=tmp_path / "vote.checkpoint.json")

    def stop_after_first_vote(event):
        if event.get("accepted"):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Runner(on_event=stop_after_first_vote).run(
            env=TalkThenVoteEnv(rounds=0),
            agents=talkers(),
            seed=0,
            checkpoint_store=checkpoint,
        )

    resumed_env = TalkThenVoteEnv(rounds=0)
    resumed_result = Runner().run(
        env=resumed_env,
        agents=talkers(),
        checkpoint_store=checkpoint,
        resume=True,
    )
    assert resumed_result == full_result
    assert resumed_env.full_state() == full_env.full_state()
