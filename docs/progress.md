# Progress

_Last updated: 2026-09-28. Milestone 1 is pushed to `main` of the private GitHub repository `masatonaut/selfplay-worlds`, and the project is verified on a CARC CPU compute node._

## DONE
- Core framework: `GameEnv`, `Interaction` (4 modes), `Runner`, `AgentOutput`, `EpisodeLogger`, trace printer.
- Coup end-to-end: 2 to 6 players, explicit phases, rules checked against two rulebook transcriptions (`docs/coup-rules.md`).
- Agents: scripted (rule-based Coup policy), random, LLM (`LLMAgent`).
- Inference: `MockBackend`, `OpenRouterBackend`, `VLLMBackend` (OpenAI-compatible, optional `llm` extra).
- `DISCUSSION` and `SIMULTANEOUS` proven with a test fixture (`tests/fixtures/talk_then_vote.py`).
- Demo: `uv run python examples/run_coup.py` (seed 0); sample log in `examples/output/`.
- Tests: rules, legality, observations, runner, logging, LLM path, fixtures, and 500 random and scripted games with invariant checks.
- CARC: verified on 2026-09-28 on a CPU compute node (`debug` partition, account `jonmay_1426`): `uv sync`, 122 passed and 1 skipped, 123 passed with `--extra llm`, and the Coup demo trace identical to the Mac. Details in `docs/carc-setup.md`.
- Docs: README, architecture, design decisions, game matrix, references, roadmap, meeting demo.
- GitHub: private repository `masatonaut/selfplay-worlds`; Milestone 1 pushed to `main` in 7 commits.
- Checked on 2026-09-24 (on a Mac): tests pass (122 passed and 1 skipped without extras, 123 passed with `--extra llm`); the Coup demo runs.

## IN PROGRESS
- Nothing.

## NEXT
1. First real-model run through OpenRouter, a few games, to see invalid-output rates and cost.
2. Decide whether to install Claude Code on CARC (not installed there; CARC's harness is).
3. Milestone 2: pick the second game (Sheriff or Deception) and verify its rules.

## OPEN QUESTIONS
- Which second game fits the research question better: Sheriff (negotiation) or Deception (discussion, roles)?
- Which models and what API budget for the first real runs?
- CARC blocks VS Code Remote-SSH on login nodes. Is the lab's Slurm proxy approach acceptable to CARC, or should we use OnDemand Code Server?
- Should this repository reuse ProjectStarter's inference utilities for consistency with the lab, or stay independent?

## KNOWN LIMITATIONS
- Only Coup is a real game. `DISCUSSION` and `SIMULTANEOUS` run only in a test fixture.
- No real model has been called yet. OpenRouter and vLLM clients are tested only against a mock and a fake local server.
- On CARC only the CPU path is verified. No GPU or vLLM run, no real OpenRouter call, and Claude Code is not installed there.
- Messages are public; there are no private or team channels.
- In Coup, talk is attached to decisions (no free chat), a claimant always reveals a card they hold, and a game ends without a winner after 100 turns (safety net, not a rule).
- The Runner is sequential; no batching or parallel episodes yet.
- Scripted agents test the machinery, not strategy.
