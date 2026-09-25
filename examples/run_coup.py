"""Play one game of Coup and print a readable trace.

Deterministic demo (no model, no network, no GPU):

    uv run python examples/run_coup.py

Other options:

    uv run python examples/run_coup.py --seed 3 --players 4
    uv run python examples/run_coup.py --quiet          # summary only
    uv run python examples/run_coup.py --full-state     # also log the god view
    uv run python examples/run_coup.py --agents random

LLM agents (optional). The mock backend runs the whole LLM path offline; the
others need `uv sync --extra llm` plus an API key or a running vLLM server:

    uv run python examples/run_coup.py --agents llm --backend mock
    uv run --extra llm python examples/run_coup.py --agents llm --backend openrouter --model <model-id>
    uv run --extra llm python examples/run_coup.py --agents llm --backend vllm --model <served-model-name>

The same seed always produces the same game (with scripted, random or mock
agents). Every run writes one JSON episode log
(default: runs/coup-seed<SEED>-<N>p.json).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from selfplay_worlds.agents.scripted import RandomAgent, ScriptedAgent
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.episodes.log import EpisodeLogger
from selfplay_worlds.episodes.trace import TracePrinter
from selfplay_worlds.games import get_game

DEFAULT_SEED = 0
"""Seed 0 shows the main mechanics in the first four turns: a failed challenge,
a block, an open block window, and a double-danger elimination."""


def build_agents(args, spec, player_ids):
    if args.agents == "random":
        return {pid: RandomAgent(seed=args.seed * 100 + i) for i, pid in enumerate(player_ids)}
    if args.agents == "llm":
        return {pid: build_llm_agent(args, spec, seed=args.seed * 100 + i) for i, pid in enumerate(player_ids)}
    return {pid: ScriptedAgent(policy=spec.scripted_policy, seed=args.seed * 100 + i) for i, pid in enumerate(player_ids)}


def build_llm_agent(args, spec, *, seed):
    from selfplay_worlds.agents.llm_agent import LLMAgent
    from selfplay_worlds.inference import MockBackend, OpenRouterBackend, VLLMBackend

    if args.backend == "mock":
        backend = MockBackend(respond=mock_model(seed))
    elif args.backend == "openrouter":
        backend = OpenRouterBackend(model=args.model)
    else:
        backend = VLLMBackend(model=args.model)
    return LLMAgent(backend=backend, spec=spec)


def mock_model(seed):
    """Stands in for a model offline: picks one of the numbered legal actions at random."""
    rng = random.Random(seed)

    def respond(messages):
        options = re.findall(r"^\d+\. ", messages[-1]["content"], flags=re.MULTILINE)
        return json.dumps({"message": None, "action": rng.randint(1, len(options))})

    return respond


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Play one game of Coup.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"game seed (default {DEFAULT_SEED})")
    parser.add_argument("--players", type=int, default=3, help="2 to 6 players (default 3)")
    parser.add_argument("--agents", choices=["scripted", "random", "llm"], default="scripted")
    parser.add_argument("--backend", choices=["mock", "openrouter", "vllm"], default="mock", help="for --agents llm")
    parser.add_argument("--model", help="model id, required for the openrouter and vllm backends")
    parser.add_argument("--quiet", action="store_true", help="print only the summary")
    parser.add_argument("--full-state", action="store_true", help="also log hidden state after every step")
    parser.add_argument("--output", type=Path, help="where to write the episode JSON")
    args = parser.parse_args(argv)
    if args.agents == "llm" and args.backend != "mock" and not args.model:
        parser.error(f"--model is required with --backend {args.backend}")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    spec = get_game("coup")
    env = spec.make_env(num_players=args.players)
    try:
        agents = build_agents(args, spec, [f"p{i}" for i in range(args.players)])
    except (ImportError, RuntimeError) as error:  # missing optional extra or API key
        print(f"error: {error}", file=sys.stderr)
        return 2
    logger = EpisodeLogger(include_full_state=args.full_state)
    runner = Runner(on_event=None if args.quiet else TracePrinter())

    result = runner.run(env=env, agents=agents, seed=args.seed, logger=logger)

    record = logger.record
    path = logger.save(args.output or Path("runs") / f"{record['episode_id']}.json")
    summary = record["result"]
    winner = env.player_name(result.winners[0])
    forced = sum(1 for e in record["events"] if e["auto"])
    print()
    print(f"Result: {winner} wins after {summary['final_public_state']['turn']} turns (seed {args.seed}).")
    print(
        f"Agent decisions: {summary['num_agent_calls']}, forced moves applied automatically: {forced}, "
        f"invalid outputs: {summary['num_invalid_outputs']}."
    )
    print(f"Episode log: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
