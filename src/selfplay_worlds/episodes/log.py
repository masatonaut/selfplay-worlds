"""One complete episode -> one JSON file.

The log keeps two things visibly apart:

* ``player_observation``: exactly what the acting player was allowed to see.
* ``full_state_after``: the god view, only when ``include_full_state=True``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.core.types import DecisionEvent, GameResult
from selfplay_worlds.inference.usage import UsageTracker

if TYPE_CHECKING:
    from selfplay_worlds.agents.base import Agent

SCHEMA_VERSION = "2.0"


class EpisodeRecorder:
    def __init__(self, *, include_full_state: bool = False, episode_id: str | None = None) -> None:
        self.include_full_state = include_full_state
        self._episode_id = episode_id
        self.record: dict = {}

    def start(self, *, env: GameEnv, agents: dict[str, Agent], seed: int | None, runner_config: dict) -> None:
        self.record = {
            "schema_version": SCHEMA_VERSION,
            "game": env.name,
            "episode_id": self._episode_id or f"{env.name}-seed{seed}-{len(env.player_ids)}p",
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "seed": seed,
            "config": {
                "env": env.config(),
                "runner": runner_config,
                "include_full_state": self.include_full_state,
            },
            "players": [
                {"id": pid, "name": env.player_name(pid), "agent": agents[pid].describe()}
                for pid in env.player_ids
            ],
            "initial_state": {
                "public": env.public_state(),
                "full_state": env.full_state() if self.include_full_state else None,
            },
            "events": [],
            "public_log": [],
            "result": None,
        }

    def record_step(self, *, event: DecisionEvent | dict, env: GameEnv) -> None:
        event = event.to_dict() if isinstance(event, DecisionEvent) else event
        entry = {"index": len(self.record["events"]), **event}
        observation = dict(entry["player_observation"])
        if isinstance(observation.get("history"), list):
            # The full text is stored once, in the top-level "public_log".
            observation["history_length"] = len(observation.pop("history"))
        entry["player_observation"] = observation
        if self.include_full_state:
            entry["full_state_after"] = env.full_state()
        self.record["events"].append(entry)

    def finish(self, *, env: GameEnv, result: GameResult, usage: UsageTracker | None = None) -> None:
        events = self.record["events"]
        self.record["public_log"] = env.public_history()
        self.record["result"] = {
            **result.to_dict(),
            "num_events": len(events),
            "num_agent_calls": sum(1 for e in events if not e["auto"] and not e["fallback"]),
            "num_invalid_outputs": sum(1 for e in events if not e["accepted"]),
            "final_public_state": env.public_state(),
            "usage": usage.state_dict() if usage else UsageTracker().state_dict(),
        }

    def state_dict(self) -> dict:
        return json.loads(json.dumps(self.record))

    def load_state_dict(self, data: dict) -> None:
        self.record = json.loads(json.dumps(data))
        self.include_full_state = bool(self.record.get("config", {}).get("include_full_state", False))

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


EpisodeLogger = EpisodeRecorder
"""Backward-compatible name. New code should say EpisodeRecorder."""
