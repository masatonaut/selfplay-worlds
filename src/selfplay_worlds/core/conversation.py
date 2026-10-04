"""ConversationGame drives one game: talk, who is asked when, actions, and the record.

It contains no game rules. It reads the open ``DialoguePhase`` from the
environment, runs the talk that phase allows, asks policies for answers, turns
each answer into the game's ``Action`` and steps the environment.

Division of labour:
    Environment       -> WHO MAY act, WHAT is legal, and what happens.
    ConversationGame  -> WHO IS ASKED FIRST, talk, retries and fallbacks.
    Policy            -> WHAT this seat says and answers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selfplay_worlds.core.env import DialogueMode, DialoguePhase, GameEnv, StepResult
from selfplay_worlds.core.persist import load_json, save_json
from selfplay_worlds.core.scheduler import RoundRobinScheduler, Scheduler

if TYPE_CHECKING:
    from selfplay_worlds.policies.base import Policy

class ConversationRecord:
    """Everything that happened at the table, in order, for every mode. Saved as JSON.

    Entry kinds:
        phase     a new dialogue phase opened
        message   table talk
        action    one answer attempt, accepted or not
        event     something the environment made public

    Policies' private reasoning is not here: each policy keeps its own.
    """

    def __init__(self, *, on_append: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.entries: list[dict[str, Any]] = []
        self.on_append = on_append

    def append(
        self,
        *,
        kind: str,
        content: Any = None,
        player_id: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        entry = {
            "index": len(self.entries),
            "kind": kind,
            "player_id": player_id,
            "content": content,
            **fields,
        }
        self.entries.append(entry)
        if self.on_append is not None:
            self.on_append(entry)
        return entry

    def save(self, *, path: str | Path) -> Path:
        return save_json(path=path, value={"entries": self.entries})

    def load(self, *, path: str | Path) -> None:
        self.entries = list(load_json(path=path)["entries"])


class ConversationGame:
    def __init__(
        self,
        *,
        env: GameEnv,
        players: dict[str, Policy],
        scheduler: Scheduler | None = None,
        max_retries: int = 2,
        skip_forced_moves: bool = True,
        max_attempts: int = 10_000,
        on_entry: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        missing, unknown = set(env.player_ids) - set(players), set(players) - set(env.player_ids)
        if missing or unknown:
            raise ValueError(f"players must match the game's seats: missing {sorted(missing)}, unknown {sorted(unknown)}")
        wrong_game = sorted(pid for pid, policy in players.items() if policy.game_name != env.name)
        if wrong_game:
            raise ValueError(f"policies for {wrong_game} were made for another game, not {env.name!r}")
        self.env = env
        self.players = dict(players)
        self.scheduler = scheduler or RoundRobinScheduler()
        self.max_retries = max_retries
        self.skip_forced_moves = skip_forced_moves
        self.max_attempts = max_attempts
        self.record = ConversationRecord(on_append=on_entry)
        self.attempts = 0
        self._last_phase_id: int | None = None
        for text in env.get_state().get("history", []):  # what the opening made public
            self.record.append(kind="event", content=text, n_steps=env.n_steps)

    # ------------------------------------------------------------------ public

    def get_conversation(self, *, player_id: str) -> list[dict[str, Any]]:
        """The table talk this player may see. All talk is public for now, so ``player_id``
        only matters once a game has private channels."""
        return [e for e in self.record.entries if e["kind"] == "message"]

    def step(self) -> None:
        """Run the open dialogue phase once: its talk, then its actions."""
        phase = self.env.get_dialogue_phase()
        if phase is None:
            return
        if phase.phase_id != self._last_phase_id:
            self._last_phase_id = phase.phase_id
            self._append(phase, kind="phase", content=phase.description, eligible=list(phase.eligible))
        if phase.mode is DialogueMode.SIMULTANEOUS:
            self._run_simultaneous(phase)
        elif phase.mode is DialogueMode.DISCUSSION:
            self._run_discussion(phase)
        else:
            self._run_in_order(phase, talk=True)

    def run(self, *, save_folder: str | Path | None = None) -> dict[str, Any]:
        """Step until the game is over, saving after every step if ``save_folder`` is given."""
        while self.env.get_dialogue_phase() is not None:
            self.step()
            if save_folder is not None:
                self.save(folder=save_folder)
        return self.env.get_state()

    # -------------------------------------------------------- scheduling modes

    def _still_open(self, phase: DialoguePhase) -> DialoguePhase | None:
        """The same phase if it is still open, otherwise None."""
        current = self.env.get_dialogue_phase()
        if current is None or current.phase_id != phase.phase_id:
            return None
        return current

    def _run_in_order(self, phase: DialoguePhase, *, talk: bool) -> None:
        """ACTION and RESPONSE_WINDOW (and the acting part of DISCUSSION).

        Ask eligible players in scheduler order. Stop as soon as the environment
        closes the phase, for example because someone challenged.
        """
        asked = 0
        for player_id in self.scheduler.order(phase=phase):
            current = self._still_open(phase)
            if current is None:
                return
            if player_id not in current.eligible:
                continue  # already responded, or no longer allowed to act
            observation = self._observe(player_id)
            if talk and not self._is_forced(observation):
                for _ in range(current.talk_rounds):
                    self._talk(current, player_id, observation)
            self._act(current, player_id, observation)
            asked += 1
        if asked == 0 and self._still_open(phase) is not None:
            raise RuntimeError(f"phase {phase.phase!r} is open but none of {list(phase.eligible)} may act")

    def _run_discussion(self, phase: DialoguePhase) -> None:
        """Talk rounds for every eligible player, then each of them acts."""
        order = [pid for pid in self.scheduler.order(phase=phase) if pid in phase.eligible]
        for _ in range(phase.talk_rounds):
            for player_id in order:
                self._talk(phase, player_id, self._observe(player_id))
        self._run_in_order(phase, talk=False)

    def _run_simultaneous(self, phase: DialoguePhase) -> None:
        """Collect every eligible player's answer BEFORE any step, so nobody sees another's choice."""
        collected = []
        for player_id in self.scheduler.order(phase=phase):
            if player_id not in phase.eligible:
                continue
            observation = self._observe(player_id)
            forced = self._is_forced(observation)
            if not forced:
                for _ in range(phase.talk_rounds):
                    self._talk(phase, player_id, observation)
            answer = None if forced else self._ask(phase, player_id, observation)
            collected.append((player_id, observation, answer))
        for player_id, observation, answer in collected:
            current = self._still_open(phase)
            if current is None or player_id not in current.eligible:
                continue  # the environment closed the phase early
            self._act(current, player_id, observation, first_answer=answer)

    # ------------------------------------------------------------ one decision

    def _observe(self, player_id: str) -> dict[str, Any]:
        """The environment's observation, plus ``"step"`` (accepted actions so far) for the policy."""
        return {**self.env.get_observation(player_id=player_id), "step": self.env.n_steps}

    def _is_forced(self, observation: dict[str, Any]) -> bool:
        return self.skip_forced_moves and len(observation.get("options") or []) == 1

    def _talk(self, phase: DialoguePhase, player_id: str, observation: dict[str, Any]) -> None:
        message = self.players[player_id].get_message(
            observation=observation, conversation=self.get_conversation(player_id=player_id)
        )
        if message:
            self._append(phase, kind="message", player_id=player_id, content=message)

    def _ask(self, phase: DialoguePhase, player_id: str, observation: dict[str, Any]) -> Any:
        return self.players[player_id].get_action(
            observation=observation, conversation=self.get_conversation(player_id=player_id)
        )

    def _act(
        self,
        phase: DialoguePhase,
        player_id: str,
        observation: dict[str, Any],
        *,
        first_answer: Any = None,
    ) -> None:
        """Ask, build the action, step; on rejection retry with the reason, then fall back."""
        forced = self._is_forced(observation)
        answer = first_answer
        for attempt in range(1, self.max_retries + 2):
            if forced:
                answer, source = {"option": 1}, "forced"
            else:
                source = "policy"
                if answer is None:
                    answer = self._ask(phase, player_id, observation)
            result = self._apply(phase, player_id, observation, answer, attempt=attempt, source=source)
            if result.accepted:
                return
            if forced:
                raise RuntimeError(f"forced move rejected for {player_id}: {result.error}")
            observation = {**observation, "feedback": result.error}
            answer = None

        if not observation.get("options"):
            raise RuntimeError(f"no acceptable answer from {player_id} and no option to fall back on: {result.error}")
        result = self._apply(
            phase, player_id, observation, {"option": 1}, attempt=self.max_retries + 2, source="fallback"
        )
        if not result.accepted:
            raise RuntimeError(f"fallback option rejected for {player_id}: {result.error}")

    def _apply(
        self,
        phase: DialoguePhase,
        player_id: str,
        observation: dict[str, Any],
        answer: Any,
        *,
        attempt: int,
        source: str,
    ) -> StepResult:
        self.attempts += 1
        if self.attempts > self.max_attempts:
            raise RuntimeError(f"game exceeded max_attempts={self.max_attempts}")
        action = None
        try:
            action = self.env.action_class.from_answer(answer=answer, player_id=player_id, observation=observation)
        except (ValueError, TypeError, KeyError) as error:
            result = StepResult(accepted=False, error=f"could not read the answer: {error}")
        else:
            result = self.env.step(player_id=player_id, action=action)
        self._append(
            phase,
            kind="action",
            player_id=player_id,
            content=action.to_dict() if action is not None else None,
            answer=_jsonable(answer),
            source=source,
            attempt=attempt,
            accepted=result.accepted,
            error=result.error,
        )
        for text in result.public_events:
            self._append(phase, kind="event", content=text)
        return result

    def _append(self, phase: DialoguePhase, **fields: Any) -> dict[str, Any]:
        return self.record.append(
            n_steps=self.env.n_steps,
            phase_id=phase.phase_id,
            phase=phase.phase,
            mode=phase.mode.value,
            **fields,
        )

    # ------------------------------------------------------------------ saving

    def save(self, *, folder: str | Path) -> Path:
        """Write the whole game to ``folder``. Call it only between ``step`` calls.

        ``game.json`` is written last and holds a hash of every other file, so a
        save interrupted halfway is detected on load instead of mixing two states.
        """
        folder = Path(folder)
        written = [policy.save(path=folder / "policies" / f"{pid}.pkl") for pid, policy in self.players.items()]
        written.append(self.env.save(path=folder / "env.pkl"))
        written.append(self.record.save(path=folder / "record.json"))
        save_json(
            path=folder / "game.json",
            value={
                "game": self.env.name,
                "game_config": self.env.game_config,
                "player_ids": self.env.player_ids,
                "policies": {pid: policy.describe() for pid, policy in self.players.items()},
                "n_steps": self.env.n_steps,
                "attempts": self.attempts,
                "last_phase_id": self._last_phase_id,
                "settings": {
                    "scheduler": self.scheduler.describe(),
                    "max_retries": self.max_retries,
                    "skip_forced_moves": self.skip_forced_moves,
                },
                "files": {path.relative_to(folder).as_posix(): _sha256(path) for path in written},
            },
        )
        return folder

    def load(self, *, folder: str | Path) -> None:
        """Adopt a game saved by ``save``. Players' models are never restored: call
        ``set_model`` on each ``Player`` afterwards."""
        folder = Path(folder)
        meta = load_json(path=folder / "game.json")
        if meta["game"] != self.env.name:
            raise ValueError(f"{folder} holds a game of {meta['game']!r}, not {self.env.name!r}")
        for name, digest in meta["files"].items():
            if _sha256(folder / name) != digest:
                raise ValueError(f"{folder / name} does not match game.json; the save was interrupted or edited")
        for pid, policy in self.players.items():
            saved_class = meta["policies"][pid]["class"]
            if saved_class != type(policy).__name__:
                raise ValueError(f"{pid} was saved as a {saved_class}, not a {type(policy).__name__}")
        self.env.load(path=folder / "env.pkl")
        for pid, policy in self.players.items():
            policy.load(path=folder / "policies" / f"{pid}.pkl")
        self.record.load(path=folder / "record.json")
        self.attempts = meta["attempts"]
        self._last_phase_id = meta["last_phase_id"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value
