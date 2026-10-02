# Design decisions

Lightweight ADR log. Each entry: **Decision / Why / Alternative / Tradeoff / Status**.

---

## ADR-01 Independent repository

- **Decision:** `selfplay-worlds` is a new, independent project. GameBoyWorlds, ProjectStarter and prime-rl are references only. No code is copied from them.
- **Why:** Nobody asked for this project to be based on those repositories. An independent codebase keeps ownership and licensing simple and lets the design follow this project's needs (multi-agent, language-heavy games) rather than a single-agent emulator or a generic template.
- **Alternative:** Generate from the ProjectStarter template, or reuse `lm_inference.py`.
- **Tradeoff:** A small amount of work is repeated (an OpenAI-compatible inference client). That client is under 100 lines, so the cost is low.
- **Status:** Accepted. See `docs/references.md`.

## ADR-02 Environment separated from Agent

- **Decision:** `GameEnv` owns the rules and state. It never calls a model. Agents only receive a player-specific observation and return an `AgentOutput`.
- **Why:** The same game must run with scripted agents, random agents, and different LLMs. Tests must not need an API key. Hidden information is safer when only the environment can see the full state.
- **Alternative:** Let the game call the model directly.
- **Tradeoff:** One extra hop (Runner) between the game and the model.
- **Status:** Accepted.

## ADR-03 Runner separated from Environment

- **Decision:** The environment says **who may act**. The Scheduler decides **who is asked first**. The Runner follows that order, manages invalid-answer retries, and applies forced moves automatically when configured.
- **Why:** In a response window, "who speaks first" changes the outcome (the first challenger wins). That is an experimental choice, not a game rule. Keeping it in the Scheduler makes turn-taking a variable we can change without touching game code.
- **Alternative:** The environment picks exactly one `current_player` every time.
- **Tradeoff:** The Runner and environment must agree on one small contract (`current_interaction`, `legal_actions`, `step`).
- **Status:** Accepted.

## ADR-04 Explicit interaction modes

- **Decision:** Every decision point is an `Interaction` with a `mode`: `SINGLE`, `RESPONSE_WINDOW`, `DISCUSSION`, or `SIMULTANEOUS`.
- **Why:** Games differ in interaction structure, not only in rules. A `current_player` field cannot express "any of these three players may challenge" or "everyone submits at once".
- **Alternative:** A single `current_player` string and an alternating loop.
- **Tradeoff:** Four modes to understand instead of one. Each mode is small.
- **Status:** Accepted. `SINGLE` and `RESPONSE_WINDOW` are used by Coup. `DISCUSSION` and `SIMULTANEOUS` are supported by the Runner and tested with small fixtures only.

## ADR-05 Generic mode plus game-specific phase

- **Decision:** `mode` is generic (framework concept). `phase` is game-specific (rule state), for example `challenge_action`, `block_action`, `challenge_block`.
- **Why:** The Runner only needs the mode to know how to schedule agents. People reading logs need the phase to know which rule is being applied.
- **Alternative:** One generic "response" phase for all Coup reactions.
- **Tradeoff:** Phase names are free-form strings, so each game documents its own.
- **Status:** Accepted.

## ADR-06 Message and action are separate

- **Decision:** `AgentOutput` has `message` (natural language) and `action` (a game-owned typed action) as separate optional fields. Actions serialize to plain dictionaries at log and checkpoint boundaries.
- **Why:** Research may compare what an agent says with what it does. The environment only validates the action. The message is recorded as public table talk.
- **Alternative:** Parse the action out of free text inside the environment.
- **Tradeoff:** LLM agents must select a structured action. The response parser lives in the agent, while structural and game-legality checks live in the environment.
- **Status:** Accepted.

## ADR-07 Observation separate from full state

- **Decision:** `observe(player_id)` returns only what that player may know. `full_state()` returns the god view and is used only by tests and the episode logger.
- **Why:** Leaking hidden cards into a prompt would silently invalidate experiments.
- **Alternative:** Give agents the full state and trust them to ignore hidden parts.
- **Tradeoff:** Each game must write an explicit observation function. Tests check that it hides what it should.
- **Status:** Accepted.

## ADR-08 One JSON file per episode

- **Decision:** A finished episode is saved as one versioned JSON file. Full god-view state per event is optional (`include_full_state`).
- **Why:** One file is easy to open, share, diff and later convert into training trajectories. Keeping full state optional keeps normal logs small and readable.
- **Alternative:** A database, or one line per event (JSONL).
- **Tradeoff:** Very long episodes produce large files. JSONL can be added later if needed.
- **Status:** Accepted, schema version `2.0`.

## ADR-09 Deterministic scripted agents

- **Decision:** Tests and the demo use seeded agents (scripted rules, random) and a seeded environment.
- **Why:** The whole framework can be tested without API keys, GPUs or cost, and the same seed always gives the same game.
- **Alternative:** Test only with real models.
- **Tradeoff:** Scripted play is not realistic play. It tests the machinery, not strategy.
- **Status:** Accepted.

## ADR-10 Small inference backend interface

- **Decision:** One method, `generate(messages=...)`, with three implementations: `MockBackend`, `OpenRouterBackend`, `VLLMBackend`. Both real backends talk to an OpenAI-compatible HTTP API.
- **Why:** OpenRouter and vLLM both expose the same chat-completions API, so one small client covers both. Credentials come only from environment variables.
- **Alternative:** Reuse ProjectStarter's inference module, or a larger framework.
- **Tradeoff:** No batching, rate limiting or async yet. Those can be added inside the backend without changing agents.
- **Status:** Accepted. `VLLMBackend` completed a full real-model Coup episode with Qwen2.5-7B-Instruct on CARC. OpenRouter has not yet been exercised with a real call.

## ADR-11 No RL integration yet

- **Decision:** No prime-rl or training code in Milestone 1.
- **Why:** The environment contract and logs must be stable first. RL is a future consumer of episodes, not part of the game logic.
- **Alternative:** Build around a training library from the start.
- **Tradeoff:** Some adapter work later.
- **Status:** Deferred to Milestone 5.

## ADR-12 Forced moves are applied by the Runner

- **Decision:** When a player has exactly one legal action and no message is required, the Runner applies it without calling the agent, and logs it as `auto`.
- **Why:** It saves model calls on non-decisions (for example revealing your only remaining card) in every game, not just Coup.
- **Alternative:** Ask the agent anyway, or special-case it inside each game.
- **Tradeoff:** The agent never "sees" forced moves. They are still in the log and in the public history.
- **Status:** Accepted, configurable (`skip_forced_moves`).

## ADR-13 The environment enforces the message policy

- **Decision:** Each interaction says whether a message is `NONE`, `OPTIONAL` or `REQUIRED`. The environment rejects outputs that break it. The Runner only uses the policy to decide whether a forced move may skip the agent and what text a fallback carries.
- **Why:** Legality, including "no talking during the vote", is a rule, and rules live in the environment.
- **Alternative:** Let the Runner strip or add messages.
- **Tradeoff:** Every game has to check the policy in `step`. It is one line.
- **Status:** Accepted. Tested with the vote phase of the test fixture.

## ADR-14 In Coup, talk is attached to decisions

- **Decision:** A Coup player can say something whenever they make a decision, including a pass. There is no free chat between decisions.
- **Why:** It keeps every episode a finite sequence of decisions, and every message has a clear place in the log. Games where talk is the main activity use the `DISCUSSION` mode.
- **Alternative:** An always-open chat channel next to the game.
- **Tradeoff:** A player cannot speak out of turn (for example the actor while others decide whether to challenge).
- **Status:** Accepted. Listed as a simplification in `docs/coup-rules.md`.

## ADR-15 LLM agents answer with the number of a legal action

- **Decision:** The prompt lists the legal actions with numbers. The model replies with JSON `{"message": ..., "action": <number>}`. The parser maps that number to the exact typed legal action and never accepts a model-invented action object. Anything unreadable becomes "no action", the environment rejects it, and the Runner retries with feedback.
- **Why:** Choosing a number is the easiest format for a model to get right, and every failure is visible in the log as a rejected output with the raw text.
- **Alternative:** Free-text actions parsed with fuzzy matching.
- **Tradeoff:** The model cannot invent actions outside the list, which is the point.
- **Status:** Accepted. The numbered-action path completed a full real-model Coup episode with Qwen2.5-7B-Instruct through vLLM on CARC with no invalid outputs or fallbacks.

## ADR-16 Typed game-specific state and actions

- **Decision:** `CoupEnv` owns one serializable `CoupState`. Coup actions are frozen `CoupAction` values with a Coup-specific enum and explicit `to_dict` and `from_dict` methods.
- **Why:** State ownership, structural validity, and the action vocabulary are visible without forcing future games into Coup fields or enums.
- **Alternative:** Keep runtime fields scattered across the environment and pass action dictionaries throughout the code.
- **Tradeoff:** Each game must define its own small state and action serializers.
- **Status:** Accepted. The generic core has only an `Action` protocol and does not contain Coup actions.

## ADR-17 Recording and checkpointing are separate

- **Decision:** `EpisodeRecorder` stores the research account of decisions. `CheckpointStore` stores versioned runtime snapshots after accepted decisions.
- **Why:** Analysis data may omit private state, while safe recovery requires game state, agent state, RNG state, usage, and runner position.
- **Alternative:** Make the episode log the live runtime state or build a full event-replay system.
- **Tradeoff:** A checkpoint contains a copy of the partial episode record so a resumed run can continue one coherent output file.
- **Status:** Accepted. Checkpoints are inspectable JSON written atomically with a temporary file and `os.replace`.

## ADR-18 Agent experience is explicit

- **Decision:** Each agent owns an `AgentState` containing the observations it saw, messages it produced, attempted actions, accepted actions, and validation feedback.
- **Why:** Agent experience is not the same thing as true game state, and each player must resume independently even when all players share one inference server.
- **Alternative:** Treat agents as stateless or serialize the live inference client.
- **Tradeoff:** Checkpoints contain repeated observation history. They never contain private reasoning or live clients.
- **Status:** Accepted. The three agents in the real Qwen CARC run had separate serialized `AgentState` values in the final checkpoint.
