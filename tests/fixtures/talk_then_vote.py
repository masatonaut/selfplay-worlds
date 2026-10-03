"""TEST FIXTURE. Not a real game, and not something we study.

A deliberately tiny "talk, then vote" game. It exists only to prove that the
framework handles the two dialogue modes that Coup does not use:

* DISCUSSION    everyone talks for ``rounds`` rounds; ConversationGame decides who
                speaks when. The environment never sees the talk: the discussion
                closes when every player has taken the (forced) "done" action.
* SIMULTANEOUS  everyone votes. Nobody may see another vote before voting.

The shape mirrors the day phase of social deduction games (Werewolf,
Deception), but there are no roles, no hidden cards and no strategy. The first
real game with these modes is planned for Milestone 2 (see docs/roadmap.md).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from selfplay_worlds.core.env import Action, DialogueMode, DialoguePhase, GameEnv, StepResult


@dataclass(frozen=True)
class FixtureAction(Action):
    type: str
    target: str | None = None

    @classmethod
    def from_answer(cls, *, answer, player_id, observation):
        if not isinstance(answer, Mapping):
            raise TypeError("an answer must be a JSON object")
        if "option" in answer:
            options = observation.get("options") or []
            choice = answer["option"]
            if not isinstance(choice, int) or not 1 <= choice <= len(options):
                raise ValueError(f"option {choice!r} is not between 1 and {len(options)}")
            answer = options[choice - 1]
        if set(answer) - {"type", "target"} or "type" not in answer:
            raise ValueError("an action needs a 'type' and at most a 'target'")
        return cls(type=answer["type"], target=answer.get("target"))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type} if self.target is None else {"type": self.type, "target": self.target}


class TalkThenVoteEnv(GameEnv):
    action_class = FixtureAction

    def __init__(self, *, game_config: dict[str, Any] | None = None) -> None:
        super().__init__(name="talk_then_vote_fixture", game_config={"num_players": 3, "rounds": 2, **(game_config or {})})

    def reset(self) -> None:
        super().reset()
        self._ids = [f"p{i}" for i in range(self.game_config["num_players"])]
        self._done: set[str] = set()
        self._votes: dict[str, str] = {}
        self._history: list[str] = []
        self._events: list[str] = []
        self._phase_id = 0
        self._outcome: dict[str, Any] | None = None
        self._open("discussion" if self.game_config["rounds"] > 0 else "vote")

    @property
    def player_ids(self) -> list[str]:
        return list(self._ids)

    def get_dialogue_phase(self) -> DialoguePhase | None:
        if self._phase == "discussion":
            return DialoguePhase(
                phase_id=self._phase_id,
                phase="discussion",
                mode=DialogueMode.DISCUSSION,
                eligible=tuple(p for p in self._ids if p not in self._done),
                talk_rounds=self.game_config["rounds"],
                description=f"Discussion: {self.game_config['rounds']} round(s).",
            )
        if self._phase == "vote":
            return DialoguePhase(
                phase_id=self._phase_id,
                phase="vote",
                mode=DialogueMode.SIMULTANEOUS,
                eligible=tuple(p for p in self._ids if p not in self._votes),
                description="Vote for one other player. Votes are revealed together.",
            )
        return None

    def _legal(self, player_id: str) -> list[FixtureAction]:
        current = self.get_dialogue_phase()
        if current is None or player_id not in current.eligible:
            return []
        if self._phase == "discussion":
            return [FixtureAction(type="done")]
        return [FixtureAction(type="vote", target=t) for t in self._ids if t != player_id]

    def get_observation(self, *, player_id: str) -> dict[str, Any]:
        return {
            "game": self.name,
            "you": player_id,
            "phase": self._phase,
            "votes_cast": len(self._votes),  # how many, never who voted for whom
            "history": list(self._history),
            "options": [action.to_dict() for action in self._legal(player_id)],
        }

    def get_state(self, *, view: str = "public") -> dict[str, Any]:
        state: dict[str, Any] = {"phase": self._phase, "history": list(self._history)}
        if view == "full":
            state["votes"] = dict(self._votes)
        outcome = self._outcome or {"done": False, "rewards": {p: 0.0 for p in self._ids}, "winners": []}
        return {**state, **outcome}

    def _step(self, *, player_id: str, action: FixtureAction) -> StepResult:
        if self._phase is None:
            return StepResult(accepted=False, error="the game is over")
        legal = self._legal(player_id)
        if not legal:
            return StepResult(accepted=False, error=f"{player_id} may not act in phase {self._phase!r}")
        if action not in legal:
            return StepResult(accepted=False, error=f"illegal action {action.to_dict()}; legal actions are {[a.to_dict() for a in legal]}")
        self._events = []
        if self._phase == "discussion":
            self._done.add(player_id)
            if len(self._done) == len(self._ids):
                self._emit("The discussion is over. Everyone votes at the same time.")
                self._open("vote")
        else:
            self._votes[player_id] = action.target
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
        self._outcome = {
            "done": True,
            "rewards": {p: 1.0 if p in winners else 0.0 for p in self._ids},
            "winners": winners,
        }
        self._phase = None

    def _open(self, phase: str) -> None:
        self._phase = phase
        self._phase_id += 1

    def _emit(self, text: str) -> None:
        self._history.append(text)
        self._events.append(text)
