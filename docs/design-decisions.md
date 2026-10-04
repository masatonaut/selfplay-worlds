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
- **Status:** Accepted. Since ADR-19 the interaction is a `DialoguePhase` and `SINGLE` is named `ACTION`. `ACTION` and `RESPONSE_WINDOW` are used by Coup. `DISCUSSION` and `SIMULTANEOUS` are supported by `ConversationGame` and tested with small fixtures only.

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
- **Status:** Superseded by ADR-20 (talk and answers are now separate calls, not two fields of one output).

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
- **Status:** Superseded by ADR-21 (a run folder with a conversation record).

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
- **Status:** Accepted, configurable (`skip_forced_moves`). Since ADR-19 `ConversationGame` applies forced moves, records them with `"source": "forced"`, and skips that player's talk outside a `DISCUSSION`.

## ADR-13 The environment enforces the message policy

- **Decision:** Each interaction says whether a message is `NONE`, `OPTIONAL` or `REQUIRED`. The environment rejects outputs that break it. The Runner only uses the policy to decide whether a forced move may skip the agent and what text a fallback carries.
- **Why:** Legality, including "no talking during the vote", is a rule, and rules live in the environment.
- **Alternative:** Let the Runner strip or add messages.
- **Tradeoff:** Every game has to check the policy in `step`. It is one line.
- **Status:** Superseded by ADR-20. The environment no longer sees talk, so there is no message policy; a phase's `talk_rounds` says whether talk happens.

## ADR-14 In Coup, talk is attached to decisions

- **Decision:** A Coup player can say something whenever they make a decision, including a pass. There is no free chat between decisions.
- **Why:** It keeps every episode a finite sequence of decisions, and every message has a clear place in the log. Games where talk is the main activity use the `DISCUSSION` mode.
- **Alternative:** An always-open chat channel next to the game.
- **Tradeoff:** A player cannot speak out of turn (for example the actor while others decide whether to challenge).
- **Status:** Superseded by ADR-20. Coup now has one talk round before each decision (except revealing a card and choosing cards to keep). Still no free chat.

## ADR-15 LLM agents answer with the number of a legal action

- **Decision:** The prompt lists the legal actions with numbers. The model replies with JSON `{"message": ..., "action": <number>}`. The parser maps that number to the exact typed legal action and never accepts a model-invented action object. Anything unreadable becomes "no action", the environment rejects it, and the Runner retries with feedback.
- **Why:** Choosing a number is the easiest format for a model to get right, and every failure is visible in the log as a rejected output with the raw text.
- **Alternative:** Free-text actions parsed with fuzzy matching.
- **Tradeoff:** The model cannot invent actions outside the list, which is the point.
- **Status:** Refined by ADR-22. The numbered-action path completed a full real-model Coup episode with Qwen2.5-7B-Instruct through vLLM on CARC with no invalid outputs or fallbacks, using the earlier `{"message", "action"}` format.

## ADR-16 Typed game-specific state and actions

- **Decision:** `CoupEnv` owns one serializable `CoupState`. Coup actions are frozen `CoupAction` values with a Coup-specific enum and explicit `to_dict` and `from_dict` methods.
- **Why:** State ownership, structural validity, and the action vocabulary are visible without forcing future games into Coup fields or enums.
- **Alternative:** Keep runtime fields scattered across the environment and pass action dictionaries throughout the code.
- **Tradeoff:** Each game must define its own small state and action serializers.
- **Status:** Accepted. The generic core has only an abstract `Action` class (`from_answer`, `to_dict`) and does not contain Coup actions.

## ADR-17 Recording and checkpointing are separate

- **Decision:** `EpisodeRecorder` stores the research account of decisions. `CheckpointStore` stores versioned runtime snapshots after accepted decisions.
- **Why:** Analysis data may omit private state, while safe recovery requires game state, agent state, RNG state, usage, and runner position.
- **Alternative:** Make the episode log the live runtime state or build a full event-replay system.
- **Tradeoff:** A checkpoint contains a copy of the partial episode record so a resumed run can continue one coherent output file.
- **Status:** Superseded by ADR-21.

## ADR-18 Agent experience is explicit

- **Decision:** Each agent owns an `AgentState` containing the observations it saw, messages it produced, attempted actions, accepted actions, and validation feedback.
- **Why:** Agent experience is not the same thing as true game state, and each player must resume independently even when all players share one inference server.
- **Alternative:** Treat agents as stateless or serialize the live inference client.
- **Tradeoff:** Checkpoints contain repeated observation history. They never contain private reasoning or live clients.
- **Status:** Superseded by ADR-21. `AgentState` recorded every observation but nothing read it; each policy now saves exactly its own state.

## ADR-19 Three layers: GameEnv, Policy, ConversationGame

- **Decision:** `GameEnv` owns rules and state. A `Policy` turns one seat's view into an answer and optional talk. `ConversationGame` runs talk, scheduling, retries, the record, and saving. `GameSpec`, `Runner`, `Agent` and `AgentOutput` are removed. Game-specific prompt text is registered by game name in `games/__init__.py`.
- **Why:** The previous lifecycle was spread across the Runner, the environment, the agents and a Coup-specific script, and no object could rebuild a run (see `report.md`). `GameSpec` bundled an environment factory, an LLM adapter and a baseline policy that only setup code used.
- **Alternative:** Keep the Runner and add an episode config object beside it.
- **Tradeoff:** Every framework-level test and the example script were rewritten. Game rules and tests did not change: 300 seeded games give identical histories, talk and winners before and after.
- **Status:** Accepted (2026-10-03, `plan.md`).

## ADR-20 Talk lives outside the environment

- **Decision:** The environment never sees talk. A `DialoguePhase` says how many `talk_rounds` come before acting. Policies talk through `get_message` and answer through `get_action` with a plain dict. The game's `Action.from_answer` turns the dict into an action; `step` checks legality and returns the reason when it rejects one.
- **Why:** Rules depend on actions, not words. Keeping talk out of the environment makes every environment smaller and lets talk be studied separately from moves.
- **Alternative:** Keep `message` as a field of the output that `step` receives.
- **Tradeoff:** A game whose move is a word (a clue) must model it as an action field. A discussion ends through the players' actions (in the fixture, a forced "done"), not by the environment counting messages.
- **Status:** Accepted.

## ADR-21 Settings in game_config, pickled state, run folders

- **Decision:** Every environment setting, the seed included, lives in `game_config`. Environments and policies pickle themselves; `GameEnv.load` refuses a save whose `game_config` differs and names the keys. `ConversationGame.save` writes a run folder (`game.json`, `env.pkl`, `record.json`, `policies/`) between steps; `game.json` is written last and holds a hash of every other file. A `Player` is pickled without its model and needs `set_model` after loading.
- **Why:** The previous checkpoint lost constructor settings on resume, rewrote a growing JSON snapshot after every step, and turned typed actions into dictionaries. Pickling keeps typed state and RNG exactly; the config check and hashes make a wrong or half-written save fail loudly.
- **Alternative:** Hand-written `to_dict` / `from_dict` for every state class.
- **Tradeoff:** Pickles are not human-readable, renaming a class breaks old saves, and a pickle must never be loaded from an untrusted source. The record stays JSON for reading.
- **Status:** Accepted.

## ADR-22 Player replies with thinking and an answer

- **Decision:** The model replies `<thinking>...</thinking><answer>...</answer>`. For a decision the answer is `{"option": <number>}` (a bare number or a game-shaped JSON object is also read); for talk it is the text to say, or empty for silence.
- **Why:** Separating reasoning from the answer keeps the answer easy to parse and makes reasoning available for analysis without making it public.
- **Alternative:** Keep the single JSON object with `message` and `action`.
- **Tradeoff:** Two model calls per decision when talk is allowed (talk, then answer). The new format has not yet been run against a real model.
- **Status:** Accepted. Tested with `MockBackend` only. Where thinking goes is ADR-23.

## ADR-23 A Player keeps its own thoughts

- **Decision:** Thinking never leaves the `Player`. Each model call is stored in `thoughts` (a dict keyed by a per-player counter, with step, phase, prompt, reply, thinking, answer and usage). Each piece of thinking is also appended to `thoughtpad`, a text with a word limit (default 400). Only the thoughtpad reaches later prompts. When it is over the limit, one extra model call rewrites it to at most half the limit, keeping what matters for the rest of the game. `ConversationGame` adds `"step"` to observations and otherwise knows nothing about thinking.
- **Why:** Reasoning is a property of one kind of policy, not of the game. Keeping it in the Player keeps `ConversationGame` and the record about the table only, and gives the model a bounded memory that it maintains itself.
- **Alternative:** Record thinking as private entries in the conversation record (the first version of ADR-22).
- **Tradeoff:** Thinking is no longer in `record.json`; it is in each Player's pickle and a readable `<pid>.thoughts.json` beside it. A summary costs an extra model call, and summarizing can drop something that later matters (the full history is kept for analysis).
- **Status:** Accepted. Tested with `MockBackend` only.
