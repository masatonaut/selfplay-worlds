"""TEST FIXTURE. Not a real game, and not something we study.

A deliberately tiny "talk, then vote" game. It exists only to prove that the
framework handles the two interaction modes that Coup does not use:

* DISCUSSION    everyone may speak. The Runner decides who speaks when; the
                environment decides when the discussion is over.
* SIMULTANEOUS  everyone votes. Nobody may see another vote before voting.

The shape mirrors the day phase of social deduction games (Werewolf,
Deception), but there are no roles, no hidden cards and no strategy. The first
real game with these modes is planned for Milestone 2 (see docs/roadmap.md).
"""

from __future__ import annotations

from collections import Counter

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.core.interaction import Interaction, InteractionMode, MessagePolicy
from selfplay_worlds.core.types import Action, AgentOutput, GameResult, StepResult

SPEAK: Action = {"type": "speak"}


class TalkThenVoteEnv(GameEnv):
    name = "talk_then_vote_fixture"

    def __init__(self, *, num_players: int = 3, rounds: int = 2) -> None:
        self._num_players = num_players
        self._rounds = rounds

    def reset(self, *, seed: int | None = None) -> None:
        self._ids = [f"p{i}" for i in range(self._num_players)]
        self._spoken = 0
        self._votes: dict[str, str] = {}
        self._history: list[str] = []
        self._events: list[str] = []
        self._interaction_id = 0
        self._result: GameResult | None = None
        self._open("discussion" if self._rounds > 0 else "vote")

    @property
    def player_ids(self) -> list[str]:
        return list(self._ids)

    def current_interaction(self) -> Interaction | None:
        if self._phase == "discussion":
            round_number = self._spoken // len(self._ids) + 1
            return Interaction(
                interaction_id=self._interaction_id,
                phase="discussion",
                mode=InteractionMode.DISCUSSION,
                eligible_players=tuple(self._ids),  # open floor: anyone may speak next
                message_policy=MessagePolicy.REQUIRED,
                description=f"Discussion, round {round_number} of {self._rounds}.",
            )
        if self._phase == "vote":
            return Interaction(
                interaction_id=self._interaction_id,
                phase="vote",
                mode=InteractionMode.SIMULTANEOUS,
                eligible_players=tuple(p for p in self._ids if p not in self._votes),
                message_policy=MessagePolicy.NONE,
                description="Vote for one other player. Votes are revealed together.",
            )
        return None

    def legal_actions(self, *, player_id: str) -> list[Action]:
        interaction = self.current_interaction()
        if interaction is None or player_id not in interaction.eligible_players:
            return []
        if self._phase == "discussion":
            return [SPEAK]
        return [{"type": "vote", "target": t} for t in self._ids if t != player_id]

    def observe(self, *, player_id: str) -> dict:
        return {
            "game": self.name,
            "you": player_id,
            "phase": self._phase,
            "votes_cast": len(self._votes),  # how many, never who voted for whom
            "history": list(self._history),
        }

    def public_history(self) -> list[str]:
        return list(self._history)

    def full_state(self) -> dict:
        return {"phase": self._phase, "spoken": self._spoken, "votes": dict(self._votes)}

    def state_dict(self) -> dict:
        return {
            "ids": list(self._ids),
            "spoken": self._spoken,
            "votes": dict(self._votes),
            "history": list(self._history),
            "interaction_id": self._interaction_id,
            "phase": self._phase,
            "result": self._result.to_dict() if self._result else None,
        }

    def load_state_dict(self, data: dict) -> None:
        self._ids = list(data["ids"])
        self._spoken = data["spoken"]
        self._votes = dict(data["votes"])
        self._history = list(data["history"])
        self._events = []
        self._interaction_id = data["interaction_id"]
        self._phase = data["phase"]
        result = data["result"]
        self._result = GameResult(**result) if result else None

    def step(self, *, player_id: str, output: AgentOutput) -> StepResult:
        interaction = self.current_interaction()
        if interaction is None:
            return StepResult(accepted=False, error="the game is over")
        if player_id not in interaction.eligible_players:
            return StepResult(accepted=False, error=f"{player_id} may not act in phase {self._phase!r}")
        self._events = []
        if self._phase == "discussion":
            return self._speak(player_id, output)
        return self._vote(player_id, output)

    def result(self) -> GameResult | None:
        return self._result

    # ------------------------------------------------------------------ phases

    def _speak(self, player_id: str, output: AgentOutput) -> StepResult:
        if output.action not in (None, SPEAK):
            return StepResult(accepted=False, error=f"illegal action {output.action}; legal actions are [{SPEAK}]")
        text = (output.message or "").strip()
        if not text:
            return StepResult(accepted=False, error="a message is required during the discussion")
        self._emit(f'{player_id} says: "{text}"')
        self._spoken += 1
        if self._spoken == self._rounds * len(self._ids):
            self._emit("The discussion is over. Everyone votes at the same time.")
            self._open("vote")
        return StepResult(accepted=True, public_events=list(self._events))

    def _vote(self, player_id: str, output: AgentOutput) -> StepResult:
        if output.message:
            return StepResult(accepted=False, error="no messages are allowed during the vote")
        legal = self.legal_actions(player_id=player_id)
        if output.action not in legal:
            return StepResult(accepted=False, error=f"illegal action {output.action}; legal actions are {legal}")
        self._votes[player_id] = output.action["target"]
        self._emit(f"{player_id} has voted.")
        if len(self._votes) == len(self._ids):
            self._finish()
        return StepResult(accepted=True, public_events=list(self._events))

    def _finish(self) -> None:
        self._emit("Votes: " + ", ".join(f"{voter} -> {target}" for voter, target in self._votes.items()) + ".")
        (top, top_count), *rest = Counter(self._votes.values()).most_common()
        voted_out = None if rest and rest[0][1] == top_count else top
        self._emit(f"{voted_out} is voted out." if voted_out else "The vote is tied. Nobody is voted out.")
        winners = [p for p in self._ids if p != voted_out]
        self._result = GameResult(
            winners=winners,
            payoffs={p: 1.0 if p in winners else 0.0 for p in self._ids},
            termination_reason="vote_finished",
        )
        self._phase = None

    # ----------------------------------------------------------------- helpers

    def _open(self, phase: str) -> None:
        self._phase = phase
        self._interaction_id += 1

    def _emit(self, text: str) -> None:
        self._history.append(text)
        self._events.append(text)
