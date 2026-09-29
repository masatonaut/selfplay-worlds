"""The Runner drives one episode.

It repeatedly asks the environment what interaction is open, asks eligible
agents in some order, and passes their outputs to ``env.step``. It contains no
game rules. The only scheduling choices it makes are:

* who is asked first (``scheduler``), which is an experimental variable,
* how invalid answers are handled (retry with feedback, then a fallback),
* whether forced moves (exactly one legal action) skip the agent call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.core.interaction import Interaction, InteractionMode, MessagePolicy
from selfplay_worlds.core.scheduler import RoundRobinScheduler, Scheduler
from selfplay_worlds.core.types import Action, AgentOutput, DecisionEvent, GameResult, action_to_dict
from selfplay_worlds.inference.usage import UsageTracker

if TYPE_CHECKING:
    from selfplay_worlds.agents.base import Agent
    from selfplay_worlds.episodes.checkpoint import CheckpointStore
    from selfplay_worlds.episodes.log import EpisodeLogger

@dataclass
class Runner:
    scheduler: Scheduler = field(default_factory=RoundRobinScheduler)
    max_retries: int = 2
    skip_forced_moves: bool = True
    max_steps: int = 10_000
    on_event: Callable[[dict], None] | None = None
    """Optional callback for every recorded step, for example a trace printer."""

    usage_tracker: UsageTracker = field(default_factory=UsageTracker)

    def config(self) -> dict:
        return {
            "scheduler": self.scheduler.describe(),
            "max_retries": self.max_retries,
            "skip_forced_moves": self.skip_forced_moves,
        }

    # ------------------------------------------------------------------ public

    def run(
        self,
        *,
        env: GameEnv,
        agents: dict[str, Agent],
        seed: int | None = None,
        logger: EpisodeLogger | None = None,
        checkpoint_store: CheckpointStore | None = None,
        resume: bool = False,
    ) -> GameResult:
        self._env, self._agents, self._logger = env, agents, logger
        self._checkpoint_store, self._seed = checkpoint_store, seed
        if resume:
            if checkpoint_store is None:
                raise ValueError("resume requires a checkpoint store")
            checkpoint = checkpoint_store.restore_runtime(
                env=env,
                agents=agents,
                usage=self.usage_tracker,
                recorder=logger,
            )
            missing = set(env.player_ids) - set(agents)
            self._steps = checkpoint["runner_state"]["steps"]
            self._pending_simultaneous = checkpoint["runner_state"].get("pending_simultaneous")
            self._seed = checkpoint["seed"]
        else:
            self.usage_tracker.reset()
            env.reset(seed=seed)
            missing = set(env.player_ids) - set(agents)
            self._steps = 0
            self._pending_simultaneous = None
            if logger is not None:
                logger.start(env=env, agents=agents, seed=seed, runner_config=self.config())
            if self.on_event is not None:
                names = {pid: env.player_name(pid) for pid in env.player_ids}
                self.on_event({"kind": "reset", "players": names, "public_events": env.public_history()})
        if missing:
            raise ValueError(f"no agent for players: {sorted(missing)}")

        while (interaction := env.current_interaction()) is not None:
            if interaction.mode is InteractionMode.SIMULTANEOUS:
                self._run_simultaneous(interaction)
            else:
                self._run_sequential(interaction)

        result = env.result()
        if result is None:
            raise RuntimeError("environment finished without a result")
        if logger is not None:
            logger.finish(env=env, result=result, usage=self.usage_tracker)
        return result

    # ------------------------------------------------------ scheduling patterns

    def _still_open(self, interaction: Interaction) -> Interaction | None:
        """The same interaction if it is still open, otherwise None."""
        current = self._env.current_interaction()
        if current is None or current.interaction_id != interaction.interaction_id:
            return None
        return current

    def _run_sequential(self, interaction: Interaction) -> None:
        """SINGLE, RESPONSE_WINDOW and DISCUSSION share one loop.

        Ask players in order. Stop as soon as the environment closes the
        interaction. For DISCUSSION the order simply repeats until then.
        """
        order = self.scheduler.order(interaction=interaction)
        while True:
            asked = 0
            for player_id in order:
                current = self._still_open(interaction)
                if current is None:
                    return
                if player_id not in current.eligible_players:
                    continue  # already responded, or no longer allowed to act
                self._take_turn(current, player_id)
                asked += 1
            if self._still_open(interaction) is None:
                return
            if asked == 0:
                raise RuntimeError(
                    f"interaction {interaction.phase!r} is open but none of {order} may act"
                )

    def _run_simultaneous(self, interaction: Interaction) -> None:
        """Query every eligible agent BEFORE any step, so nobody sees another's choice."""
        pending = self._pending_simultaneous
        if pending is None or pending["interaction_id"] != interaction.interaction_id:
            entries = []
            for player_id in self.scheduler.order(interaction=interaction):
                observation = self._env.observe(player_id=player_id)
                legal = self._env.legal_actions(player_id=player_id)
                first = self._first_output(interaction, player_id, observation, legal)
                entries.append(
                    {
                        "player_id": player_id,
                        "observation": observation,
                        "legal": [action_to_dict(action) for action in legal],
                        "output": first.to_dict(),
                    }
                )
            pending = {"interaction_id": interaction.interaction_id, "entries": entries}
            self._pending_simultaneous = pending

        entries = list(pending["entries"])
        for index, entry in enumerate(entries):
            player_id = entry["player_id"]
            current = self._still_open(interaction)
            if current is None or player_id not in current.eligible_players:
                continue  # the environment closed the interaction early
            self._pending_simultaneous = {
                "interaction_id": interaction.interaction_id,
                "entries": entries[index + 1 :],
            }
            observation = entry["observation"]
            legal = entry["legal"]
            first = AgentOutput(**entry["output"])
            self._submit(current, player_id, observation, legal, first)
        self._pending_simultaneous = None

    # ------------------------------------------------------------ one decision

    def _take_turn(self, interaction: Interaction, player_id: str) -> None:
        observation = self._env.observe(player_id=player_id)
        legal = self._env.legal_actions(player_id=player_id)
        first = self._first_output(interaction, player_id, observation, legal)
        self._submit(interaction, player_id, observation, legal, first)

    def _first_output(
        self, interaction: Interaction, player_id: str, observation: dict, legal: list[Action]
    ) -> AgentOutput:
        if not legal:
            raise RuntimeError(f"{player_id} is eligible in {interaction.phase!r} but has no legal action")
        if self._is_forced(interaction, legal):
            return AgentOutput(action=legal[0], metadata={"auto": True})
        if self._agents[player_id].describe().get("model"):
            self.usage_tracker.check_before_call()
        return self._agents[player_id].act(
            observation=observation, interaction=interaction, legal_actions=legal, feedback=None
        )

    def _is_forced(self, interaction: Interaction, legal: list[Action]) -> bool:
        return (
            self.skip_forced_moves
            and len(legal) == 1
            and interaction.message_policy is not MessagePolicy.REQUIRED
        )

    def _submit(
        self,
        interaction: Interaction,
        player_id: str,
        observation: dict,
        legal: list[Action],
        output: AgentOutput,
    ) -> None:
        """Step the environment; on rejection retry with feedback, then fall back."""
        for attempt in range(1, self.max_retries + 2):
            result = self._env.step(player_id=player_id, output=output)
            self._remember(player_id, observation, output, result.accepted, result.error)
            self.usage_tracker.record(output.metadata)
            self._record(interaction, player_id, observation, output, result, attempt=attempt)
            if result.accepted:
                return
            if attempt <= self.max_retries:
                if self._agents[player_id].describe().get("model"):
                    self.usage_tracker.check_before_call()
                output = self._agents[player_id].act(
                    observation=observation,
                    interaction=interaction,
                    legal_actions=legal,
                    feedback=result.error,
                )

        fallback = AgentOutput(
            action=legal[0],
            message="(no valid response)" if interaction.message_policy is MessagePolicy.REQUIRED else None,
            metadata={"fallback": True, "reason": result.error},
        )
        result = self._env.step(player_id=player_id, output=fallback)
        self._remember(player_id, observation, fallback, result.accepted, result.error)
        self._record(interaction, player_id, observation, fallback, result, attempt=self.max_retries + 2)
        if not result.accepted:
            raise RuntimeError(f"fallback action rejected for {player_id}: {result.error}")

    def _record(self, interaction, player_id, observation, output, result, *, attempt: int) -> None:
        self._steps += 1
        if self._steps > self.max_steps:
            raise RuntimeError(f"episode exceeded max_steps={self.max_steps}")
        decision = DecisionEvent(
            interaction=interaction.to_dict(),
            actor=player_id,
            observation=observation,
            output=output,
            attempt=attempt,
            accepted=result.accepted,
            error=result.error,
            public_events=tuple(result.public_events),
        )
        event = decision.to_dict()
        if self._logger is not None:
            self._logger.record_step(event=decision, env=self._env)
        if result.accepted and self._checkpoint_store is not None:
            self._checkpoint_store.save_runtime(
                env=self._env,
                agents=self._agents,
                runner_state={
                    "steps": self._steps,
                    "pending_simultaneous": self._pending_simultaneous,
                },
                usage=self.usage_tracker,
                recorder=self._logger,
                seed=self._seed,
                config={
                    "game": self._env.name,
                    "env": self._env.config(),
                    "runner": self.config(),
                    "agents": {player_id: agent.describe() for player_id, agent in self._agents.items()},
                },
            )
        if self.on_event is not None:
            self.on_event(event)

    def _remember(self, player_id, observation, output, accepted, feedback) -> None:
        agent = self._agents[player_id]
        agent.record_attempt(
            observation=observation,
            output=output,
            accepted=accepted,
            feedback=feedback,
        )
