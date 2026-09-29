"""The demo command must keep working."""

import importlib.util
import json
from pathlib import Path

from selfplay_worlds.episodes.log import SCHEMA_VERSION
from selfplay_worlds.core.types import GameResult

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "run_coup.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("run_coup", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_runs_and_writes_one_episode_file(tmp_path, capsys):
    out = tmp_path / "episode.json"
    assert _load_example().main(["--quiet", "--output", str(out)]) == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["episode_id"] == "coup-seed0-3p"
    assert "Result: Carol wins after 14 turns (seed 0)." in capsys.readouterr().out


def test_demo_trace_is_deterministic(tmp_path, capsys):
    run_coup = _load_example()
    run_coup.main(["--output", str(tmp_path / "a.json")])
    first = capsys.readouterr().out.split("Episode log:")[0]
    run_coup.main(["--output", str(tmp_path / "b.json")])
    second = capsys.readouterr().out.split("Episode log:")[0]
    assert first == second
    assert "Bob challenges Carol's claim to be the Duke." in first


def test_offline_llm_path_runs(tmp_path):
    assert _load_example().main(["--quiet", "--agents", "llm", "--backend", "mock", "--output", str(tmp_path / "llm.json")]) == 0


def test_resume_recreates_checkpointed_agent_type():
    run_coup = _load_example()
    args = run_coup.parse_args(["--resume", "checkpoint.json"])
    payload = {
        "config": {
            "agents": {
                "p0": {"type": "RandomAgent", "model": None, "backend": None},
                "p1": {"type": "RandomAgent", "model": None, "backend": None},
            }
        }
    }
    run_coup.apply_resume_config(args, payload)
    assert args.agents == "random"


def test_turn_limit_summary_does_not_assume_a_winner():
    run_coup = _load_example()
    result = GameResult(winners=[], payoffs={"p0": 0.0}, termination_reason="turn_limit")
    assert run_coup.result_line(env=None, result=result, turn=100, seed=4) == (
        "Result: no winner after 100 turns (turn_limit, seed 4)."
    )
