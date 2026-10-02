# SelfPlayWorlds: Design and Implementation Overview

## Motivation

SelfPlayWorlds is a reusable runtime for strategic games in which multiple LLM agents play against or alongside one another. The runtime separates game rules, player observations, model inference, scheduling, research records, and recovery so that each part can be tested and replaced independently.

Previous game-scouting work compared bluffing, deduction, negotiation, and communication games. The main implementation difficulty is not simply game length. It is the structure of each interaction:

- Who acts next?
- Who can react?
- Are decisions sequential or simultaneous?
- Does an agent choose a structured action, communicate freely, or do both?
- Can the result be evaluated directly from game rules?

These questions determine the runtime contract more directly than a game's theme or number of turns.

## Why Coup is the first implementation

Coup has a small state and action space, but it still includes bluffing, hidden information, challenges, blocks, and challenges to blocks. Its outcomes are objectively checkable from published rules. This makes it compact enough to test thoroughly while exercising more than a simple alternating-turn loop.

One action can open a sequence of conditional reactions:

```text
action
→ challenge
→ block
→ challenge block
→ state update
```

That sequence tests ordinary turns and response windows in one complete game.

## Runtime model

```text
Game State
→ Interaction
→ Scheduler
→ Agent
→ message + action
→ validate + step
→ new Game State
```

- **Game State** is the complete, serializable truth for one episode. The environment owns it and exposes only player-specific observations.
- **Interaction** describes the decision that is currently open, including its phase, interaction mode, eligible players, and message policy.
- **Scheduler** orders players whom the environment has already declared eligible. This makes speaker order replaceable without moving game rules into the runner.
- **Agent** receives an observation and the exact legal actions, then returns an `AgentOutput` containing a public message, a structured action, or both.
- **Validation and step** remain authoritative in the environment. A valid decision updates the game state and opens the next interaction.
- **Runner** connects these components, records each attempt, and checkpoints after accepted decisions. It contains no Coup rules or model-specific behavior.

## Design decisions from the initial discussion

| Initial design concern | Current implementation | Rationale / status |
|---|---|---|
| Game source of truth | `GameEnv` owns a game-specific serializable state such as `CoupState`. | The environment is authoritative. Agents receive observations rather than hidden state. |
| Conversation or decision situation | `Interaction` | One type represents the open decision, so there is no duplicate `ConversationSituation` abstraction. |
| Who may act | `Interaction.eligible_players`, determined by the environment | Eligibility follows game rules. |
| Who is queried first | `Scheduler` | Query order is an experimental policy and can change without editing game rules. |
| Action Creator | `GameEnv.legal_actions()` plus a game-specific typed action | Coup returns exact `CoupAction` values. Each future game owns its own action vocabulary. |
| `valid(action)` | Action deserialization checks structure; `GameEnv.validate_action()` checks current-state legality; `step()` checks again. | A structurally valid action can still be illegal in the current state, and callers cannot bypass validation. |
| Message versus action | `AgentOutput(message, action)` | Public language and structured behavior remain independently measurable. |
| Prompt ownership | The game renders rules and a player observation; `LLMAgent` adds common response instructions. | Game-specific knowledge stays with the game, while model transport stays generic. Hidden cards are never included in another player's prompt. |
| Per-agent observation history | One serializable `AgentState` per agent | Each agent retains only its own experience, without private chain-of-thought or a live inference client. |
| Logging | `DecisionEvent` and `EpisodeRecorder` | The episode record captures accepted and rejected attempts for research analysis but does not own runtime state. |
| Checkpoint and resume | `CheckpointStore` | A versioned, atomic snapshot stores game state, agent states, runner state, usage, RNG state, and the partial episode record. |
| Usage and budget tracking | `UsageTracker` | It aggregates calls, tokens, latency, and provider-reported cost, and can enforce simple hard limits. |
| vLLM integration | `VLLMBackend` through the OpenAI-compatible inference boundary | Game rules and agents do not depend on vLLM. The same path can use another backend without changing Coup. |

The four supported interaction modes are:

- `SINGLE`: one eligible player makes one decision.
- `RESPONSE_WINDOW`: eligible players are queried until the environment closes the window.
- `DISCUSSION`: speakers cycle until the environment ends discussion.
- `SIMULTANEOUS`: all outputs are collected before any are applied.

## Current implementation status

### Validated in a real game

- Coup
- `SINGLE`
- `RESPONSE_WINDOW`

Coup supports 2 to 6 players, hidden information, typed actions, challenges, blocks, challenges to blocks, per-agent state, episode recording, usage tracking, and deterministic checkpoint and resume.

### Validated with a real model

The completed baseline used:

- `Qwen/Qwen2.5-7B-Instruct`
- vLLM on CARC
- one A40 GPU
- one full three-player Coup episode
- 15 real model calls
- challenge, block, and challenge-block phases
- 0 invalid outputs
- 0 retries
- 0 fallbacks
- a checkpoint and validation report that both passed

### Implemented and test-supported only

- `DISCUSSION`
- `SIMULTANEOUS`

These modes are exercised by `tests/fixtures/talk_then_vote.py`. That fixture proves scheduling, message-policy enforcement, discussion termination, and simultaneous collection. It is not a second complete game and does not establish real-model validation for those modes.

## Model validation status

The Qwen real-model baseline is complete. Validation of the original target, `google/gemma-4-31B-it`, is in progress on CARC. Gemma success is not claimed until an actual full episode and its artifacts pass validation.

## Repository map

| Responsibility | Main location |
|---|---|
| `GameEnv` and `GameSpec` | `src/selfplay_worlds/core/env.py` |
| `Interaction` and interaction modes | `src/selfplay_worlds/core/interaction.py` |
| `Scheduler` | `src/selfplay_worlds/core/scheduler.py` |
| `Runner` | `src/selfplay_worlds/core/runner.py` |
| `Agent` and `AgentOutput` | `src/selfplay_worlds/agents/base.py` |
| `AgentState` | `src/selfplay_worlds/agents/state.py` |
| LLM agent and reply parsing | `src/selfplay_worlds/agents/llm_agent.py` |
| Coup state | `src/selfplay_worlds/games/coup/state.py` |
| Coup actions | `src/selfplay_worlds/games/coup/actions.py` |
| Coup environment and rules | `src/selfplay_worlds/games/coup/env.py` |
| Coup prompt rendering | `src/selfplay_worlds/games/coup/prompts.py` |
| Inference interface and generation config | `src/selfplay_worlds/inference/base.py` |
| OpenAI-compatible and vLLM backends | `src/selfplay_worlds/inference/openai_compatible.py` |
| Usage tracking | `src/selfplay_worlds/inference/usage.py` |
| Episode recording | `src/selfplay_worlds/episodes/log.py` |
| Checkpointing | `src/selfplay_worlds/episodes/checkpoint.py` |

For the exact decision call path, see `docs/repo-walkthrough.md`. For detailed runtime behavior and serialization boundaries, see `docs/architecture.md`. Current validation milestones are tracked in `docs/progress.md`.
