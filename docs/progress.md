# Progress

_Last updated: 2026-10-02._

## DONE
- Core framework: `GameEnv`, `Interaction` (4 modes), `Runner`, `AgentOutput`, `EpisodeRecorder`, trace printer.
- Coup end-to-end: 2 to 6 players, explicit phases, rules checked against two rulebook transcriptions (`docs/coup-rules.md`).
- Agents: scripted (rule-based Coup policy), random, LLM (`LLMAgent`).
- Inference: `MockBackend`, `OpenRouterBackend`, `VLLMBackend` (OpenAI-compatible, optional `llm` extra).
- `DISCUSSION` and `SIMULTANEOUS` proven with a test fixture (`tests/fixtures/talk_then_vote.py`).
- Demo: `uv run python examples/run_coup.py` (seed 0); sample log in `examples/output/`.
- Tests: rules, legality, observations, runner, logging, LLM path, fixtures, and 500 random and scripted games with invariant checks.
- CARC CPU path: the full 135-test suite and the scripted Coup demo pass on the pushed commit. Details are in `docs/carc-setup.md`.
- Docs: README, architecture, design decisions, game matrix, references, roadmap, meeting demo.
- GitHub: private repository `masatonaut/selfplay-worlds`; Milestone 1 pushed to `main` in 7 commits.
- Checked on 2026-09-24 (on a Mac): tests pass (122 passed and 1 skipped without extras, 123 passed with `--extra llm`); the Coup demo runs.
- Architecture: `CoupState`, `CoupAction`, `CoupPhase`, `AgentState`, `Scheduler`, `DecisionEvent`, `EpisodeRecorder`, `CheckpointStore`, `GenerationConfig`, and `UsageTracker` are explicit. Deterministic checkpoint and resume is tested.
- Local verification: 134 passed and 1 skipped without the optional LLM extra; 135 passed with `--extra llm`. The seed 0 scripted demo still produces Carol as winner after 14 turns.
- Real-model baseline: CARC job `12555139` completed a full three-player Coup episode with `Qwen/Qwen2.5-7B-Instruct` through vLLM on one A40. Alice (`p0`) won after 5 turns with 15 real model calls, 18 accepted events, 3 forced moves, 0 invalid outputs, 0 retries, and 0 fallbacks. Challenge, block, and challenge-block phases all occurred. Usage was 10,883 input tokens and 180 output tokens. The checkpoint and validation report passed.
- The proven launcher isolates the shared Python 3.12 vLLM process from the project's Python 3.11 process by exporting `PYTHONPATH` only until vLLM starts, then unsetting it before SelfPlayWorlds runs.

## IN PROGRESS
- CARC validation targets `google/gemma-4-31B-it` on two same-node A40 GPUs with tensor parallelism. The exact model is cached and the batch is pending. No Gemma success is claimed yet.

## NEXT
1. Complete and inspect the pending Gemma 4 validation without adding a duplicate GPU job.
2. Complete the second real environment so other researchers can begin using the framework. Deception is a sensible proposal because it exercises `DISCUSSION`, but the project has not selected it yet.
3. Verify the selected second game's rules before implementation.

## OPEN QUESTIONS
- Should Deception be environment 2, or should another game take priority?
- What minimum real-model evaluation should every new environment pass before others use it?
- CARC blocks VS Code Remote-SSH on login nodes. Is the lab's Slurm proxy approach acceptable to CARC, or should we use OnDemand Code Server?
- Should this repository reuse ProjectStarter's inference utilities for consistency with the lab, or stay independent?

## KNOWN LIMITATIONS
- Only Coup is a real game. `DISCUSSION` and `SIMULTANEOUS` run only in a test fixture.
- vLLM on CARC is validated with Qwen2.5-7B-Instruct. Gemma 4 31B is still pending, and OpenRouter has not been validated with a real call.
- Messages are public; there are no private or team channels.
- In Coup, talk is attached to decisions (no free chat), a claimant always reveals a card they hold, and a game ends without a winner after 100 turns (safety net, not a rule).
- The Runner is sequential; no batching or parallel episodes yet.
- Scripted agents test the machinery, not strategy.
