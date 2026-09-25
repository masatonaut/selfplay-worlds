"""The Runner drives one episode.

It repeatedly asks the environment what interaction is open, asks eligible
agents in some order, and passes their outputs to ``env.step``. It contains no
game rules. The only scheduling choices it makes are:

* who is asked first (``order_policy``), which is an experimental variable,
* how invalid answers are handled (retry with feedback, then a fallback),
* whether forced moves (exactly one legal action) skip the agent call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.core.interaction import Interaction, InteractionMode, MessagePolicy
from selfplay_worlds.core.types import Action, AgentOutput, GameResult

if TYPE_CHECKING:
    from selfplay_worlds.agents.base import Agent
    from selfplay_worlds.episodes.log import EpisodeLogger

OrderPolicy = Callable[[Interaction], list[str]]


def env_order(interaction: Interaction) -> list[str]:
    """Default: ask eligible players in the order the environment listed them."""
    return list(interaction.eligible_players)


@dataclass
class Runner:
    order_policy: OrderPolicy = env_order
    max_retries: int = 2
    skip_forced_moves: bool = True
    max_steps: int = 10_000
    on_event: Callable[[dict], None] | None = None
    """Optional callback for every recorded step, for example a trace printer."""

    def config(self) -> dict:
        return {
            "order_policy": getattr(self.order_policy, "__name__", repr(self.order_policy)),
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
    ) -> GameResult:
        env.reset(seed=seed)
        missing = set(env.player_ids) - set(agents)
        if missing:
            raise ValueError(f"no agent for players: {sorted(missing)}")
        self._env, self._agents, self._logger, self._steps = env, agents, logger, 0
        if logger is not None:
            logger.start(env=env, agents=agents, seed=seed, runner_config=self.config())
        if self.on_event is not None:
            names = {pid: env.player_name(pid) for pid in env.player_ids}
            self.on_event({"kind": "reset", "players": names, "public_events": env.public_history()})

        while (interaction := env.current_interaction()) is not None:
            if interaction.mode is InteractionMode.SIMULTANEOUS:
                self._run_simultaneous(interaction)
            else:
                self._run_sequential(interaction)

        result = env.result()
        if result is None:
            raise RuntimeError("environment finished without a result")
        if logger is not None:
            logger.finish(env=env, result=result)
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
        order = self.order_policy(interaction)
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
        collected = []
        for player_id in self.order_policy(interaction):
            observation = self._env.observe(player_id=player_id)
            legal = self._env.legal_actions(player_id=player_id)
            first = self._first_output(interaction, player_id, observation, legal)
            collected.append((player_id, observation, legal, first))
        for player_id, observation, legal, first in collected:
            current = self._still_open(interaction)
            if current is None or player_id not in current.eligible_players:
                continue  # the environment closed the interaction early
            self._submit(current, player_id, observation, legal, first)

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
            self._record(interaction, player_id, observation, output, result, attempt=attempt)
            if result.accepted:
                return
            if attempt <= self.max_retries:
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
        self._record(interaction, player_id, observation, fallback, result, attempt=self.max_retries + 2)
        if not result.accepted:
            raise RuntimeError(f"fallback action rejected for {player_id}: {result.error}")

    def _record(self, interaction, player_id, observation, output, result, *, attempt: int) -> None:
        self._steps += 1
        if self._steps > self.max_steps:
            raise RuntimeError(f"episode exceeded max_steps={self.max_steps}")
        event = {
            "kind": "step",
            "interaction": interaction.to_dict(),
            "actor": player_id,
            "player_observation": observation,
            "output": output.to_dict(),
            "auto": bool(output.metadata.get("auto")),
            "fallback": bool(output.metadata.get("fallback")),
            "attempt": attempt,
            "accepted": result.accepted,
            "error": result.error,
            "public_events": list(result.public_events),
        }
        if self._logger is not None:
            self._logger.record_step(event=event, env=self._env)
        if self.on_event is not None:
            self.on_event(event)
