"""The demo command must keep working."""

import importlib.util
import json
from pathlib import Path

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
    assert record["schema_version"] == "1.0"
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
