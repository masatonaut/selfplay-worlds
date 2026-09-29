"""Play one game of Coup and print a readable trace.

Deterministic demo (no model, no network, no GPU):

    uv run python examples/run_coup.py

Other options:

    uv run python examples/run_coup.py --seed 3 --players 4
    uv run python examples/run_coup.py --quiet          # summary only
    uv run python examples/run_coup.py --full-state     # also log the god view
    uv run python examples/run_coup.py --agents random
    uv run python examples/run_coup.py --resume runs/coup-seed0-3p.checkpoint.json

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
from selfplay_worlds.episodes.checkpoint import CheckpointStore
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
    from selfplay_worlds.inference import (
        GEMMA_4_GENERATION_CONFIG,
        GenerationConfig,
        MockBackend,
        OpenRouterBackend,
        VLLMBackend,
    )

    if args.backend == "mock":
        backend = MockBackend(respond=mock_model(seed))
    elif args.backend == "openrouter":
        backend = OpenRouterBackend(model=args.model)
    else:
        backend = VLLMBackend(model=args.model)
    gemma = args.model == "google/gemma-4-31B-it"
    recommended = GEMMA_4_GENERATION_CONFIG if gemma else GenerationConfig()
    generation = GenerationConfig(
        max_tokens=args.max_tokens,
        temperature=args.temperature if args.temperature is not None else recommended.temperature,
        top_p=args.top_p if args.top_p is not None else recommended.top_p,
        top_k=args.top_k if args.top_k is not None else recommended.top_k,
        reasoning=False,
    )
    return LLMAgent(
        backend=backend,
        spec=spec,
        generation_config=generation,
        structured_output=args.structured_output,
    )


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
    parser.add_argument("--max-tokens", type=int, default=300, help="maximum output tokens per model call")
    parser.add_argument("--temperature", type=float, help="sampling temperature")
    parser.add_argument("--top-p", type=float, help="nucleus sampling threshold")
    parser.add_argument("--top-k", type=int, help="top-k sampling (sent as an OpenAI-compatible extension)")
    parser.add_argument("--structured-output", action="store_true", help="request JSON-schema constrained output")
    parser.add_argument("--max-calls", type=int, help="stop before another model call after this many calls")
    parser.add_argument("--max-input-tokens", type=int, help="stop before another call after this many input tokens")
    parser.add_argument("--max-output-tokens", type=int, help="stop before another call after this many output tokens")
    parser.add_argument("--quiet", action="store_true", help="print only the summary")
    parser.add_argument("--full-state", action="store_true", help="also log hidden state after every step")
    parser.add_argument("--output", type=Path, help="where to write the episode JSON")
    parser.add_argument("--checkpoint", type=Path, help="checkpoint path (default: beside the episode log)")
    parser.add_argument("--resume", type=Path, help="resume from this checkpoint")
    args = parser.parse_args(argv)
    if args.agents == "llm" and args.backend != "mock" and not args.model:
        parser.error(f"--model is required with --backend {args.backend}")
    return args


def apply_resume_config(args, payload):
    """Recreate the checkpointed agent setup for the documented one-flag resume path."""
    descriptions = list(payload.get("config", {}).get("agents", {}).values())
    agent_types = {description.get("type") for description in descriptions}
    if len(agent_types) != 1:
        raise ValueError("resume requires one consistent agent type in the checkpoint")
    agent_type = agent_types.pop()
    if agent_type == "ScriptedAgent":
        args.agents = "scripted"
    elif agent_type == "RandomAgent":
        args.agents = "random"
    elif agent_type == "LLMAgent":
        args.agents = "llm"
        description = descriptions[0]
        args.backend = description["backend"]
        args.model = description["model"]
        generation = description["generation"]
        args.max_tokens = generation["max_tokens"]
        args.temperature = generation["temperature"]
        args.top_p = generation["top_p"]
        args.top_k = generation["top_k"]
        args.structured_output = generation["structured_output"]
    else:
        raise ValueError(f"unsupported checkpoint agent type {agent_type!r}")


def result_line(*, env, result, turn: int, seed: int) -> str:
    if result.winners:
        return f"Result: {env.player_name(result.winners[0])} wins after {turn} turns (seed {seed})."
    return f"Result: no winner after {turn} turns ({result.termination_reason}, seed {seed})."


def main(argv=None) -> int:
    args = parse_args(argv)
    resume_payload = CheckpointStore(path=args.resume).load() if args.resume else None
    if resume_payload is not None:
        args.seed = resume_payload["seed"]
        args.players = len(resume_payload["agent_states"])
        try:
            apply_resume_config(args, resume_payload)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    spec = get_game("coup")
    env = spec.make_env(num_players=args.players)
    try:
        agents = build_agents(args, spec, [f"p{i}" for i in range(args.players)])
    except (ImportError, RuntimeError) as error:  # missing optional extra or API key
        print(f"error: {error}", file=sys.stderr)
        return 2
    logger = EpisodeLogger(include_full_state=args.full_state)
    from selfplay_worlds.inference import UsageLimits, UsageTracker

    usage = UsageTracker(
        limits=UsageLimits(
            max_calls=args.max_calls,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
        )
        if any(value is not None for value in (args.max_calls, args.max_input_tokens, args.max_output_tokens))
        else None
    )
    runner = Runner(on_event=None if args.quiet else TracePrinter(), usage_tracker=usage)
    if args.output:
        output_path = args.output
    elif args.resume:
        resumed_name = args.resume.name.replace(".checkpoint.json", ".json")
        output_path = (
            args.resume.with_name(resumed_name)
            if resumed_name != args.resume.name
            else args.resume.with_suffix(".episode.json")
        )
    else:
        output_path = Path("runs") / f"coup-seed{args.seed}-{args.players}p.json"
    checkpoint_path = args.resume or args.checkpoint or output_path.with_suffix(".checkpoint.json")
    checkpoint_store = CheckpointStore(path=checkpoint_path)

    try:
        result = runner.run(
            env=env,
            agents=agents,
            seed=args.seed,
            logger=logger,
            checkpoint_store=checkpoint_store,
            resume=args.resume is not None,
        )
    except KeyboardInterrupt:
        print(f"\nInterrupted. Resume with --resume {checkpoint_path}", file=sys.stderr)
        return 130

    record = logger.record
    path = logger.save(output_path)
    summary = record["result"]
    forced = sum(1 for e in record["events"] if e["auto"])
    print()
    print(result_line(env=env, result=result, turn=summary["final_public_state"]["turn"], seed=args.seed))
    print(
        f"Agent decisions: {summary['num_agent_calls']}, forced moves applied automatically: {forced}, "
        f"invalid outputs: {summary['num_invalid_outputs']}."
    )
    print(f"Episode log: {path}")
    print(f"Checkpoint: {checkpoint_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
