# Roadmap

Each milestone ends with something that runs and is tested. Dates are not fixed. This roadmap promises working infrastructure, not research results.

## M1: generic framework and Coup (this milestone)

- [x] `GameEnv`, `Interaction`, `Runner`, `Agent`, `InferenceBackend`, `EpisodeLogger`
- [x] Coup end-to-end with explicit phases, 2 to 6 players, rule tests and random-game stress tests
- [x] `DISCUSSION` and `SIMULTANEOUS` proven with a test fixture
- [x] One JSON file per episode; readable terminal trace; deterministic demo
- [x] Optional LLM agents: mock, OpenRouter, vLLM (only the mock has been run)
- [x] CARC setup documented; to be verified on CARC

## M2: a second real game with a different interaction structure

- Candidates: Sheriff of Nottingham (negotiation, simultaneous loading) or Deception (discussion, roles, a silent player). See `docs/game-format-matrix.md`.
- Verify its rules against the rulebook first, like `docs/coup-rules.md`.
- Success test: the second game needs **no changes** to the Runner, agents or logger, or the changes are small and justified.

## M3: multiple LLM backends and controlled evaluation

- Run real models through OpenRouter and a local vLLM server on CARC.
- Controlled settings: fixed seeds, fixed prompts, recorded model versions, temperature, token counts and cost.
- Baseline metrics from the logs: win rate against scripted agents, invalid-output rate, bluff rate, challenge accuracy.

## M4: repeated self-play and evaluation

- Run many episodes (models against themselves and each other), with batching and parallel episodes.
- Tools to aggregate episode JSON files into tables.
- Check whether the Runner's order policy changes outcomes (first-responder advantage).

## M5: reinforcement learning, if needed

- Convert episode logs into training trajectories.
- Evaluate prime-rl or a similar framework as the training side. The environment contract stays the same; RL only consumes episodes.
