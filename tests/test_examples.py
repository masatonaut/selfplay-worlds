"""The demo command must keep working."""

import importlib.util
import json
from pathlib import Path

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.games.coup import CoupEnv

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "run_coup.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("run_coup", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_runs_and_saves_one_run_folder(tmp_path, capsys):
    out = tmp_path / "run"
    assert _load_example().main(["--quiet", "--out", str(out)]) == 0
    meta = json.loads((out / "game.json").read_text(encoding="utf-8"))
    assert meta["game"] == "coup" and meta["game_config"]["seed"] == 0
    assert (out / "record.json").exists() and (out / "env.pkl").exists()
    assert "Result: Carol wins after 14 turns (seed 0)." in capsys.readouterr().out


def test_demo_trace_is_deterministic(tmp_path, capsys):
    run_coup = _load_example()
    run_coup.main(["--out", str(tmp_path / "a")])
    first = capsys.readouterr().out.split("Saved game:")[0]
    run_coup.main(["--out", str(tmp_path / "b")])
    second = capsys.readouterr().out.split("Saved game:")[0]
    assert first == second
    assert "Bob challenges Carol's claim to be the Duke." in first


def test_offline_llm_path_runs(tmp_path):
    assert _load_example().main(["--quiet", "--policies", "llm", "--backend", "mock", "--out", str(tmp_path / "llm")]) == 0


def _interrupt_after(steps, *, folder, players):
    game = ConversationGame(env=CoupEnv(game_config={"num_players": 3, "seed": 0}), players=players)
    for _ in range(steps):
        game.step()
    game.save(folder=folder)


def test_resume_finishes_an_interrupted_game_exactly(tmp_path, capsys):
    run_coup = _load_example()
    run_coup.main(["--quiet", "--out", str(tmp_path / "full")])
    full = capsys.readouterr().out.split("Saved game:")[0]

    args = run_coup.parse_args([])
    _interrupt_after(6, folder=tmp_path / "half", players=run_coup.build_players(args, ["p0", "p1", "p2"]))
    assert run_coup.main(["--quiet", "--resume", str(tmp_path / "half")]) == 0
    assert capsys.readouterr().out.split("Saved game:")[0] == full
    full_record = json.loads((tmp_path / "full" / "record.json").read_text(encoding="utf-8"))
    half_record = json.loads((tmp_path / "half" / "record.json").read_text(encoding="utf-8"))
    assert half_record == full_record


def test_resume_reattaches_models_to_llm_players(tmp_path):
    run_coup = _load_example()
    args = run_coup.parse_args(["--policies", "llm", "--backend", "mock"])
    _interrupt_after(3, folder=tmp_path / "llm", players=run_coup.build_players(args, ["p0", "p1", "p2"]))
    assert run_coup.main(["--quiet", "--resume", str(tmp_path / "llm")]) == 0
    meta = json.loads((tmp_path / "llm" / "game.json").read_text(encoding="utf-8"))
    assert all(p["class"] == "Player" and p["backend"] == "mock" for p in meta["policies"].values())


def test_resume_of_a_missing_folder_is_a_clean_error(tmp_path, capsys):
    assert _load_example().main(["--resume", str(tmp_path / "nothing")]) == 2
    assert "error:" in capsys.readouterr().err


def test_turn_limit_summary_does_not_assume_a_winner():
    run_coup = _load_example()
    final = {"winners": [], "turn": 100, "termination_reason": "turn_limit"}
    assert run_coup.result_line(final=final, names={}, seed=4) == "Result: no winner after 100 turns (turn_limit, seed 4)."
