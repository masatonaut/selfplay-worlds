# Repository walkthrough

## The 11 questions

| Concept | Question | Code answer |
|---|---|---|
| `GameSpec` | What game is this? | `core/env.py::GameSpec` points to the environment constructor, rules, observation renderer, and default scripted policy. |
| `CoupState` | What is true now? | `games/coup/state.py::CoupState` holds the complete serializable game state. |
| `Interaction` | What decision is open? | `core/interaction.py::Interaction` names the phase, scheduling mode, eligible players, and message policy. |
| `Scheduler` | Who acts next? | `core/scheduler.py::Scheduler` orders eligible players. `RoundRobinScheduler` is the deterministic default. |
| `AgentState` | What has this agent experienced? | `agents/state.py::AgentState` stores observations, produced messages, attempted actions, accepted actions, and validation feedback. Public history is already inside each saved observation, so it is not duplicated in a second field. It never stores private reasoning. |
| `Agent` | Who decides? | `agents/base.py::Agent` is the decision interface. Scripted, random, and LLM agents implement it. |
| Prompt | What does the model see? | `games/coup/prompts.py::render_observation` renders only the player observation and numbered legal actions. |
| Inference | Which model answers? | `inference/base.py::InferenceBackend` is the model boundary. `inference/openai_compatible.py` connects OpenRouter or vLLM. |
| Action | What did it choose? | `games/coup/actions.py::CoupAction` is Coup's typed action. The model selects its number from the legal list. |
| EpisodeRecord | What happened? | `episodes/log.py::EpisodeRecorder` stores typed decision events as research JSON. |
| Checkpoint | How do we resume? | `episodes/checkpoint.py::CheckpointStore` atomically stores runtime snapshots after accepted decisions. |

## One complete call path

1. `examples/run_coup.py::main` creates a `GameSpec`, `CoupEnv`, one agent per player, an `EpisodeRecorder`, a `CheckpointStore`, and a `Runner`.
2. `core/runner.py::Runner.run` calls `CoupEnv.current_interaction`.
3. `RoundRobinScheduler.order` returns the query order for the eligible players.
4. `Runner._take_turn` calls `CoupEnv.observe` and `CoupEnv.legal_actions`.
5. `LLMAgent.act` calls `games/coup/prompts.py::render_observation` with that observation and the exact legal `CoupAction` objects.
6. `VLLMBackend.generate` or another `InferenceBackend.generate` returns model text and usage metadata.
7. `agents/llm_agent.py::parse_reply` reads the numbered choice and maps it back to one exact legal action.
8. `CoupEnv.step` calls `CoupEnv.validate_action` again, then applies the phase handler.
9. `Runner._record` creates a `DecisionEvent` and sends it to `EpisodeRecorder.record_step`.
10. After an accepted decision, `CheckpointStore.save_runtime` writes a versioned snapshot with a temporary file and `os.replace`.
11. The loop asks `CoupEnv.current_interaction` again.

## Challenge example: Tax

Alice chooses the typed action `CoupAction(type=TAX)`. `CoupEnv._on_action` records the Duke claim and opens `CoupPhase.CHALLENGE_ACTION`. The new `Interaction` is a `RESPONSE_WINDOW` containing the other living players in seat order. The scheduler decides who is asked first. A pass removes that player from the window. A challenge calls `CoupEnv._resolve_challenge`. If Alice has a Duke, she reveals it, returns it to the deck, draws a replacement, and the challenger enters `LOSE_INFLUENCE`. If she does not have a Duke, Alice enters `LOSE_INFLUENCE` and Tax fails. The environment decides all outcomes. The runner knows none of these Coup rules.

## Whiteboard concepts mapped to code

| Whiteboard idea | Implementation |
|---|---|
| Static rules and prompt rendering | `GameSpec` plus `games/coup/prompts.py` |
| True world state | `CoupState` owned by `CoupEnv` |
| Current conversation situation | `Interaction`; there is no duplicate `ConversationSituation` |
| Who may act | `Interaction.eligible_players`, decided by the environment |
| Who is asked first | `Scheduler`, selected by the runner configuration |
| Agent memory | One `AgentState` per `Agent` |
| Model transport | `InferenceBackend` |
| Audit trail | `DecisionEvent` and `EpisodeRecorder` |
| Recovery | `CheckpointStore` |
| Cost and limits | `UsageTracker` |

## Short answers

### Where is the prompt?

Coup rules and observation rendering are in `src/selfplay_worlds/games/coup/prompts.py`. Common instructions and the model call are in `LLMAgent`.

### Who chooses the next agent?

The environment says who is eligible. The `Scheduler` chooses their query order. The runner follows that order.

### Where are legal actions made?

`CoupEnv.legal_actions` creates typed `CoupAction` objects from the current `CoupState`.

### Where is an action validated?

`CoupEnv.validate_action` separates structure from game legality. `CoupEnv.step` always calls it, so callers cannot bypass validation.

### Where does game state live?

Exactly one `CoupState` lives inside `CoupEnv`. Observations are filtered views of it.

### Why does logging happen around Runner?

The runner sees the observation, agent output, environment result, retries, and inference metadata together. The recorder only records those facts and never changes the game.

### Why is checkpointing separate from logging?

The episode record answers what happened. The checkpoint answers how execution resumes. A checkpoint contains private runtime state and RNG state, while a research log can omit the god view.

### Why does each agent need state?

Each player has a different experience. Separate state prevents one agent's observation or memory from becoming another agent's memory, and makes resume deterministic without serializing a model client.

### How is discussion different from a normal turn?

A normal `SINGLE` interaction asks one player once. A `DISCUSSION` interaction cycles through scheduler order until the environment closes it. Speaker scheduling is an experimental variable.

### How would another game be added?

Add its environment, state, action type, prompts, and `GameSpec` in a new game folder. Coup does not change. The runner and inference backend do not change if the game uses the existing interaction modes.

### Where does vLLM connect?

`VLLMBackend` points the OpenAI client at `VLLM_BASE_URL`. It sends model messages and generation settings only. It never sees game state objects.

### What came from ProjectStarter and GameBoyWorlds?

ProjectStarter reinforced the small OpenAI compatible inference boundary, environment variable credentials, and explicit token metadata. We did not import its broad rate limiter or retry hierarchy because this runner is synchronous and local vLLM failures should be visible. GameBoyWorlds reinforced keeping game specific code in separate folders and exposing observations and actions through a common environment boundary. No source code was copied.

## One sentence per major class

`GameSpec` identifies a game and its model facing text. `CoupEnv` enforces Coup rules. `CoupState` stores the truth. `Interaction` describes the open decision. `Scheduler` orders eligible actors. `AgentState` stores one player's experience. `Agent` chooses an output. `InferenceBackend` calls a model. `CoupAction` represents a well formed Coup move. `DecisionEvent` describes one attempt. `EpisodeRecorder` writes the audit record. `CheckpointStore` restores execution. `UsageTracker` counts inference consumption. `Runner` connects them in that order.

## Complete concept map

| Concept | Where | One responsibility |
|---|---|---|
| `GameSpec` | `core/env.py` | Names a game and connects its constructor, rules, prompt renderer, and scripted policy. |
| `GameEnv` | `core/env.py` | Defines the shared environment contract without prescribing a game's state fields. |
| Game state | Game-specific, such as `games/coup/state.py` | Stores the dynamic truth for one game. There is intentionally no generic `GameState` base class. |
| `CoupState` | `games/coup/state.py` | Stores all serializable Coup runtime truth and RNG state. |
| `Interaction` and `InteractionMode` | `core/interaction.py` | Describe the open decision and its generic scheduling pattern. |
| `Scheduler` | `core/scheduler.py` | Orders actors whom the environment already declared eligible. |
| `Runner` | `core/runner.py` | Orchestrates decisions, retries, recording, and safe checkpoints. |
| `Agent` and `AgentState` | `agents/base.py`, `agents/state.py` | Choose outputs and retain one player's serializable experience. |
| Prompt builder | `games/coup/prompts.py`, `agents/llm_agent.py` | Render game-specific observations, then assemble common model instructions. |
| `InferenceBackend` and `VLLMBackend` | `inference/base.py`, `inference/openai_compatible.py` | Transport model messages and return generated text plus usage metadata. |
| `GenerationConfig` | `inference/base.py` | Holds explicit provider-independent sampling settings. |
| Game action | `core/types.py::Action` protocol | Requires game-owned actions to serialize without defining their vocabulary. |
| `CoupAction` | `games/coup/actions.py` | Represents one structurally valid Coup action as a frozen typed value. |
| `validate_action` and `step` | `games/coup/env.py` | Separate structural parsing from current-state legality, then apply the transition. |
| `DecisionEvent` | `core/types.py` | Represents one accepted or rejected decision attempt. |
| `EpisodeRecorder` | `episodes/log.py` | Records what happened for later analysis. |
| `CheckpointStore` | `episodes/checkpoint.py` | Saves and restores serializable runtime snapshots. |
| `UsageTracker` | `inference/usage.py` | Aggregates model calls, tokens, latency, reported cost, and simple limits. |

## Design-only examples for future games

Sheriff would add `games/sheriff/` with a `SheriffState`, `SheriffAction`, and `SheriffEnv`. Its phases could cover private bag loading with simultaneous actions, declarations, negotiation as `DISCUSSION`, and a sheriff inspection or pass as `SINGLE`. Objective rules would calculate goods, penalties, and the result. `Runner`, `Scheduler`, and inference would not change.

Deception would add `games/deception/` with a `DeceptionState`, `DeceptionAction`, and `DeceptionEnv`. Its phases could cover private roles and clues, scheduler-controlled `DISCUSSION`, a simultaneous or sequential accusation phase, and objective rule-based resolution. The game would own clue visibility and role observations. It would not require Coup changes or a new inference interface.

## Strict architecture review

1. There is one interaction concept. No `ConversationSituation` duplicate was added.
2. Every new abstraction is used by Coup, the discussion fixture, or both. The old free function ordering compatibility layer was removed after review.
3. `Runner` contains no Coup terms or rules.
4. Agents receive observations and legal actions only. They never receive `CoupState` or `full_state`.
5. `EpisodeRecorder` owns only the research record. `CheckpointStore` owns snapshot encoding and atomic replacement.
6. Checkpoints contain plain dictionaries, lists, numbers, strings, and nulls. They never contain live backends or clients.
7. `Interaction` was retained instead of adding a duplicate situation class. A full event-sourcing layer, actor runtime, registry framework, database, and PettingZoo adapter were rejected.
8. Every major class has a one sentence description above.
9. A Sheriff or Deception environment can define its own state, actions, phases, observations, and prompts without editing Coup.
10. A different inference backend can implement `InferenceBackend.generate` without editing game rules.

The main remaining architectural compromise is that `CoupEnv` keeps private forwarding properties such as `_turn` and `_phase` so the existing rule handlers remain readable while `CoupState` is the single storage object. They are aliases, not duplicate state. A future rewrite could use `self.state.phase` everywhere, but that would add churn without changing the model.
