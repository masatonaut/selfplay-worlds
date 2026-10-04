"""Play one game of Coup and print a readable trace.

Deterministic demo (no model, no network, no GPU):

    uv run python examples/run_coup.py

Other options:

    uv run python examples/run_coup.py --seed 3 --players 4
    uv run python examples/run_coup.py --quiet          # summary only
    uv run python examples/run_coup.py --policies random
    uv run python examples/run_coup.py --resume runs/coup-seed0-3p

LLM players (optional). The mock backend runs the whole LLM path offline; the
others need `uv sync --extra llm` plus an API key or a running vLLM server:

    uv run python examples/run_coup.py --policies llm --backend mock
    uv run --extra llm python examples/run_coup.py --policies llm --backend openrouter --model <model-id>
    uv run --extra llm python examples/run_coup.py --policies llm --backend vllm --model <served-model-name>

The same seed always produces the same game (with scripted, random or mock
policies). Every run is saved after every step to one folder
(default: runs/coup-seed<SEED>-<N>p/), which --resume continues.
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.core.persist import load_json
from selfplay_worlds.episodes.trace import TracePrinter
from selfplay_worlds.games.coup import CoupEnv, CoupHeuristicPolicy
from selfplay_worlds.inference import (
    GEMMA_4_GENERATION_CONFIG,
    GenerationConfig,
    MockBackend,
    UsageLimits,
)
from selfplay_worlds.policies import Player, RandomPolicy

DEFAULT_SEED = 0
"""Seed 0 shows the main mechanics in the first four turns: a failed challenge,
a block, an open block window, and a double-danger elimination."""


def build_backend(*, backend: str, model: str | None, seed: int):
    if backend == "mock":
        return MockBackend(respond=mock_model(seed))
    from selfplay_worlds.inference import OpenRouterBackend, VLLMBackend

    if backend == "openrouter":
        return OpenRouterBackend(model=model)
    return VLLMBackend(model=model)


def mock_model(seed):
    """Stands in for a model offline: stays silent, keeps short notes, and picks a numbered option at random."""
    rng = random.Random(seed)

    def respond(messages):
        prompt = messages[-1]["content"]
        if "Rewrite your notes" in prompt:
            return "<answer>Nothing certain yet; I have been choosing at random.</answer>"
        if "moment to talk" in prompt:
            return "<thinking>Nothing to say.</thinking><answer></answer>"
        options = re.findall(r"^\d+\. ", prompt, flags=re.MULTILINE)
        return f'<thinking>Picking at random.</thinking><answer>{{"option": {rng.randint(1, len(options))}}}</answer>'

    return respond


def usage_limits(args) -> UsageLimits | None:
    limits = (args.max_calls, args.max_input_tokens, args.max_output_tokens)
    if all(value is None for value in limits):
        return None
    return UsageLimits(max_calls=args.max_calls, max_input_tokens=args.max_input_tokens, max_output_tokens=args.max_output_tokens)


def build_players(args, player_ids):
    seeds = {pid: args.seed * 100 + i for i, pid in enumerate(player_ids)}
    if args.policies == "random":
        return {pid: RandomPolicy(game_name="coup", seed=seeds[pid]) for pid in player_ids}
    if args.policies == "scripted":
        return {pid: CoupHeuristicPolicy(seed=seeds[pid]) for pid in player_ids}
    recommended = GEMMA_4_GENERATION_CONFIG if args.model == "google/gemma-4-31B-it" else GenerationConfig()
    generation = GenerationConfig(
        max_tokens=args.max_tokens,
        temperature=args.temperature if args.temperature is not None else recommended.temperature,
        top_p=args.top_p if args.top_p is not None else recommended.top_p,
        top_k=args.top_k if args.top_k is not None else recommended.top_k,
    )
    return {
        pid: Player(
            game_name="coup",
            model=build_backend(backend=args.backend, model=args.model, seed=seeds[pid]),
            generation_config=generation,
            usage_limits=usage_limits(args),
        )
        for pid in player_ids
    }


def rebuild_players(meta):
    """Empty policies of the saved classes. ``ConversationGame.load`` fills in their state."""
    players = {}
    for pid, description in meta["policies"].items():
        kind = description["class"]
        if kind == "CoupHeuristicPolicy":
            players[pid] = CoupHeuristicPolicy()
        elif kind == "RandomPolicy":
            players[pid] = RandomPolicy(game_name="coup")
        elif kind == "Player":
            players[pid] = Player(game_name="coup", model=None)
        else:
            raise ValueError(f"unsupported saved policy {kind!r} for {pid}")
    return players


def reattach_models(players, meta, args) -> None:
    """Models are never saved: give every Player a fresh backend, and the caller's budget."""
    for i, (pid, policy) in enumerate(players.items()):
        if isinstance(policy, Player):
            description = meta["policies"][pid]
            policy.set_model(model=build_backend(backend=description["backend"], model=description["model"], seed=meta["game_config"]["seed"] * 100 + i))
            if usage_limits(args) is not None:
                policy.usage.limits = usage_limits(args)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Play one game of Coup.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"game seed (default {DEFAULT_SEED})")
    parser.add_argument("--players", type=int, default=3, help="2 to 6 players (default 3)")
    parser.add_argument("--policies", choices=["scripted", "random", "llm"], default="scripted")
    parser.add_argument("--backend", choices=["mock", "openrouter", "vllm"], default="mock", help="for --policies llm")
    parser.add_argument("--model", help="model id, required for the openrouter and vllm backends")
    parser.add_argument("--max-tokens", type=int, default=300, help="maximum output tokens per model call")
    parser.add_argument("--temperature", type=float, help="sampling temperature")
    parser.add_argument("--top-p", type=float, help="nucleus sampling threshold")
    parser.add_argument("--top-k", type=int, help="top-k sampling (sent as an OpenAI-compatible extension)")
    parser.add_argument("--max-calls", type=int, help="per player: stop before another model call after this many")
    parser.add_argument("--max-input-tokens", type=int, help="per player: stop before another call after this many input tokens")
    parser.add_argument("--max-output-tokens", type=int, help="per player: stop before another call after this many output tokens")
    parser.add_argument("--quiet", action="store_true", help="print only the summary")
    parser.add_argument("--out", type=Path, help="run folder (default: runs/coup-seed<SEED>-<N>p)")
    parser.add_argument("--resume", type=Path, help="continue the game saved in this run folder")
    args = parser.parse_args(argv)
    if args.policies == "llm" and args.backend != "mock" and not args.model:
        parser.error(f"--model is required with --backend {args.backend}")
    return args


def result_line(*, final: dict, names: dict[str, str], seed) -> str:
    if final["winners"]:
        return f"Result: {names[final['winners'][0]]} wins after {final['turn']} turns (seed {seed})."
    return f"Result: no winner after {final['turn']} turns ({final['termination_reason']}, seed {seed})."


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.resume:
            folder = args.resume
            meta = load_json(path=folder / "game.json")
            env = CoupEnv(game_config=meta["game_config"])
            players = rebuild_players(meta)
        else:
            folder = args.out or Path("runs") / f"coup-seed{args.seed}-{args.players}p"
            env = CoupEnv(game_config={"num_players": args.players, "seed": args.seed})
            players = build_players(args, env.player_ids)
    except (ImportError, RuntimeError, ValueError, FileNotFoundError) as error:  # missing extra, API key or save
        print(f"error: {error}", file=sys.stderr)
        return 2

    names = {pid: env.player_name(pid) for pid in env.player_ids}
    trace = None if args.quiet else TracePrinter(names=names)
    # On resume the opening was already printed when the game first ran, so the trace starts after load.
    game = ConversationGame(env=env, players=players, on_entry=None if args.resume else trace)
    if args.resume:
        game.load(folder=folder)
        reattach_models(players, meta, args)
        game.record.on_append = trace
        if trace is not None:
            print(f"Resuming {folder} at turn {env.get_state()['turn']}.")

    try:
        final = game.run(save_folder=folder)
    except KeyboardInterrupt:
        print(f"\nInterrupted. Resume with --resume {folder}", file=sys.stderr)
        return 130

    actions = [e for e in game.record.entries if e["kind"] == "action"]
    print()
    print(result_line(final=final, names=names, seed=env.game_config["seed"]))
    print(
        f"Decisions asked: {sum(e['source'] == 'policy' for e in actions)}, "
        f"forced moves applied automatically: {sum(e['source'] == 'forced' for e in actions)}, "
        f"invalid answers: {sum(not e['accepted'] for e in actions)}."
    )
    print(f"Saved game: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
