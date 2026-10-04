# Progress

_Last updated: 2026-10-03._

## DONE
- Core framework (redesigned 2026-10-03, see below): `GameEnv`, `Action`, `DialoguePhase` (4 modes), `ConversationGame`, `ConversationRecord`, trace printer.
- Coup end-to-end: 2 to 6 players, explicit phases, rules checked against two rulebook transcriptions (`docs/coup-rules.md`).
- Policies: `CoupHeuristicPolicy` (rule-based), `RandomPolicy`, `ReplayPolicy`, and the LLM-backed `Player`.
- Inference: `MockBackend`, `OpenRouterBackend`, `VLLMBackend` (OpenAI-compatible, optional `llm` extra).
- `DISCUSSION` and `SIMULTANEOUS` proven with a test fixture (`tests/fixtures/talk_then_vote.py`).
- Demo: `uv run python examples/run_coup.py` (seed 0); sample log in `examples/output/`.
- Tests: rules, legality, observations, the GameEnv contract, ConversationGame, policies and the LLM path, save and resume, fixtures, and 500 random and scripted games with invariant checks.
- CARC CPU path: the full 135-test suite and the scripted Coup demo pass on the pushed commit. Details are in `docs/carc-setup.md`.
- Docs: README, architecture, design decisions, game matrix, references, roadmap, meeting demo.
- GitHub: private repository `masatonaut/selfplay-worlds`; Milestone 1 pushed to `main` in 7 commits.
- Checked on 2026-09-24 (on a Mac): tests pass (122 passed and 1 skipped without extras, 123 passed with `--extra llm`); the Coup demo runs.
- Redesign (2026-10-03, `plan.md`): `GameSpec`, `Runner`, `Agent`, `AgentState`, `EpisodeRecorder` and `CheckpointStore` were replaced by three layers. `GameEnv` holds every setting in `game_config` and pickles itself, refusing a save with a different config. Policies return answer dicts and talk through `get_message`; `Player` parses `<thinking>` and `<answer>` and is saved without its model. `ConversationGame` runs talk and actions, keeps the conversation record, and saves a run folder after every step. Verified: 164 passed and 1 skipped without extras, 165 passed with `--extra llm`; 300 seeded games (random and heuristic, 2 to 6 players) give the same public history, talk and winners as the engine before the redesign; the seed 0 demo trace is unchanged.
- Local verification before the redesign: 134 passed and 1 skipped without the optional LLM extra; 135 passed with `--extra llm`. The seed 0 scripted demo still produces Carol as winner after 14 turns.
- Real-model baseline (before the redesign, earlier prompt format): CARC job `12555139` completed a full three-player Coup episode with `Qwen/Qwen2.5-7B-Instruct` through vLLM on one A40. Alice (`p0`) won after 5 turns with 15 real model calls, 18 accepted events, 3 forced moves, 0 invalid outputs, 0 retries, and 0 fallbacks. Challenge, block, and challenge-block phases all occurred. Usage was 10,883 input tokens and 180 output tokens. The checkpoint and validation report passed.
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
- vLLM on CARC was validated with Qwen2.5-7B-Instruct on the earlier prompt format. The current `Player` prompt has not been run against a real model. Gemma 4 31B is still pending, and OpenRouter has not been validated with a real call.
- Messages are public; there are no private or team channels. A `Player` keeps its thinking to itself (ADR-23).
- In Coup, talk is one round before each decision (no free chat), a claimant always reveals a card they hold, and a game ends without a winner after 100 turns (safety net, not a rule).
- ConversationGame is sequential; no batching, parallel episodes or multi-game runner yet.
- Scripted policies test the machinery, not strategy.
