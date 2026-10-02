# Design review for DJ

This document maps the original whiteboard questions to the current implementation. The design stays small: game rules live in the environment, model access lives behind one backend interface, and the runner only connects the pieces.

## Whiteboard concepts to code

| Original concept | Current implementation | Meaning |
|---|---|---|
| GAME | `GameSpec` and `GameEnv` | `GameSpec` describes the game and its prompt renderer. `GameEnv` defines the rules interface. |
| game state | A game-specific serializable state such as `CoupState` | The environment owns exactly one source of truth. There is no universal state class with Coup fields. |
| Conversation Situation | `Interaction` | The open decision: game phase, interaction mode, eligible players, and message policy. |
| acts or decisions | `Agent.act()` inside the current `Interaction` | The agent receives its observation and the exact legal actions for that decision. |
| who may act | `Interaction.eligible_players` | The environment determines eligibility from the game rules. |
| who is asked first or speaker order | `Scheduler` | The scheduler orders players who are already eligible. This is an experimental policy. |
| Action Creator | `GameEnv.legal_actions()` plus a game-specific typed action | Coup returns `CoupAction` values. A future game owns a different action vocabulary. |
| params | Typed action fields | For example, a Coup action has an action type and an optional target. |
| `valid(action)` | Action parsing plus `GameEnv.validate_action()` | The action type checks structure. The environment checks legality in the current state. `step()` checks again. |
| what the agent says versus what it does | `AgentOutput(message, action)` | Public natural language and the structured move are separate fields. |
| conversation or rounds of dialogue | `InteractionMode` | The four modes are `SINGLE`, `RESPONSE_WINDOW`, `DISCUSSION`, and `SIMULTANEOUS`. |
| prompt ownership | Game-specific renderer plus common `LLMAgent` instructions | The game renders only a player observation. `LLMAgent` adds the numbered-action response format. |
| model call | `InferenceBackend` | `MockBackend`, `OpenRouterBackend`, and `VLLMBackend` share one small boundary. |
| per-agent history | `AgentState` | Every agent separately stores observations, attempted and accepted actions, messages, and validation feedback. It never stores private reasoning. |
| logging | `DecisionEvent` plus `EpisodeRecorder` | The record answers what happened and includes rejected attempts and inference metadata. |
| checkpoint or resume | `CheckpointStore` | A versioned snapshot stores game state, agent states, runner state, usage, RNG state, and the partial record. |
| budget or usage | `UsageTracker` | It counts calls, input tokens, output tokens, and latency, and can enforce simple hard limits. |

## Deliberate differences from the sketch

### One situation class

`Interaction` is the implementation of Conversation Situation. Adding another class with the same fields would create two names for one responsibility.

### Eligibility and order are different decisions

The environment decides who **may** act because that is a game rule. The scheduler decides who is **asked first** because speaker order can be an experimental variable. The runner follows the scheduler and does not contain Coup rules.

### Structure and legality are different checks

An action can be structurally well formed but illegal now. `CoupAction.from_dict()` checks shape and vocabulary. `CoupEnv.validate_action()` checks the current state. `CoupEnv.step()` always validates again so a caller cannot bypass legality.

### Speech and action are different data

An agent can say one thing and choose another. `AgentOutput` therefore stores `message` and `action` separately. This makes claims, persuasion, and behavior independently measurable.

### Research records and recovery snapshots are different

`EpisodeRecorder` stores the research account of what happened. `CheckpointStore` stores enough private runtime state to resume safely. The recorder does not own the environment, and a checkpoint never contains a live model client.

## Interaction modes

| Mode | Meaning | Current evidence |
|---|---|---|
| `SINGLE` | One eligible player makes one decision | Used by Coup and exercised with a real model |
| `RESPONSE_WINDOW` | Eligible players are queried until the environment closes the window | Used by Coup challenges and blocks and exercised with a real model |
| `DISCUSSION` | Speakers cycle until the environment ends discussion | Generic runner support and test fixture only |
| `SIMULTANEOUS` | All outputs are collected before any are applied | Generic runner support and test fixture only |

`tests/fixtures/talk_then_vote.py` is not a claimed real discussion game. It proves scheduling, message policy, discussion termination, and simultaneous collection.

## Current validation levels

### Real game and real model

- Coup
- `SINGLE`
- `RESPONSE_WINDOW`
- Qwen2.5-7B-Instruct through vLLM on CARC

The Qwen baseline completed a full three-player episode. Alice (`p0`) won after 5 turns. It made 15 real model calls and recorded 18 accepted events, including 3 forced moves. Challenge, block, and challenge-block phases occurred. There were 0 invalid outputs, retries, or fallbacks. Usage was 10,883 input tokens and 180 output tokens. The checkpoint and validation report passed.

### Generic and test-supported only

- `DISCUSSION`
- `SIMULTANEOUS`
- `tests/fixtures/talk_then_vote.py`

### Not yet claimed

- A real Deception environment
- A real Sheriff environment
- RL or self-training
- Private or team communication channels
- A completed Gemma 4 31B run

The Gemma target is `google/gemma-4-31B-it`. CARC job `12558939` is currently pending for priority, so the repository does not claim success yet.

## Exact decision path

```text
CoupEnv.current_interaction()
→ RoundRobinScheduler.order()
→ CoupEnv.observe(actor)
→ CoupEnv.legal_actions(actor)
→ LLMAgent.act()
→ games/coup/prompts.py::render_observation()
→ VLLMBackend.generate()
→ parse_reply()
→ CoupEnv.validate_action()
→ CoupEnv.step()
→ DecisionEvent
→ EpisodeRecorder.record_step()
→ CheckpointStore.save_runtime()
```

The model selects a number from the displayed legal-action list. That number maps back to one exact typed action. The model does not invent an action dictionary.

## What DJ should decide next

The immediate product priority is a second real environment so other researchers can begin using the framework. Deception is a sensible proposal because it would validate `DISCUSSION` in a real social game, but it is only a proposal until DJ selects it.

Useful decisions are:

1. Is Deception the second environment, or should another game come first?
2. What is the minimum real-model evaluation required before an environment is ready for other researchers?
3. Are public messages sufficient for the first two environments, or must private or team channels be added now?
