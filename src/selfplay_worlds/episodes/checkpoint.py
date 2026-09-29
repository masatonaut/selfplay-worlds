"""Versioned JSON snapshots for recovery, separate from episode records."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from selfplay_worlds.inference.usage import UsageTracker

CHECKPOINT_SCHEMA_VERSION = "1.0"


class CheckpointStore:
    def __init__(self, *, path: str | Path) -> None:
        self.path = Path(path)

    def save(
        self,
        *,
        game_state: dict[str, Any],
        agent_states: dict[str, dict[str, Any]],
        runner_state: dict[str, Any],
        usage_state: dict[str, Any],
        episode_record: dict[str, Any] | None,
        seed: int | None,
        config: dict[str, Any],
    ) -> Path:
        payload = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "game_state": game_state,
            "agent_states": agent_states,
            "runner_state": runner_state,
            "usage_state": usage_state,
            "episode_record": episode_record,
            "seed": seed,
            "config": config,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return self.path

    def load(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(f"unsupported checkpoint schema {payload.get('schema_version')!r}")
        return payload

    def save_runtime(
        self,
        *,
        env,
        agents,
        runner_state: dict[str, Any],
        usage: UsageTracker,
        recorder,
        seed: int | None,
        config: dict[str, Any],
    ) -> Path:
        """Snapshot serializable project state. Live clients are never included."""
        return self.save(
            game_state=env.state_dict(),
            agent_states={player_id: agent.state_dict() for player_id, agent in agents.items()},
            runner_state=runner_state,
            usage_state=usage.state_dict(),
            episode_record=recorder.state_dict() if recorder is not None else None,
            seed=seed,
            config=config,
        )

    def restore_runtime(self, *, env, agents, usage: UsageTracker, recorder) -> dict[str, Any]:
        payload = self.load()
        env.load_state_dict(payload["game_state"])
        for player_id, state in payload["agent_states"].items():
            if player_id not in agents:
                raise ValueError(f"checkpoint has no configured agent for {player_id}")
            agents[player_id].load_state_dict(state)
        usage.load_state_dict(payload["usage_state"])
        if recorder is not None and payload["episode_record"] is not None:
            recorder.load_state_dict(payload["episode_record"])
        return {"runner_state": payload["runner_state"], "seed": payload["seed"]}
