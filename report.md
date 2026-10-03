# selfplay-worlds: code review and walkthrough

Reviewed at commit `fc2b69d` on 2026-10-03. The test suite passes (134 passed, 1 skipped). Every bug listed below was found by reading the code and confirmed by a small probe script unless it says otherwise.

The goal this review measures against: **a system that can emulate environments and play many games in a clean process, where the framework handles checkpointing, logging, initialization and game flexibility well.**

---

## 0. What changed after this review

The review below describes the code at `fc2b69d`. Following it, the framework was redesigned according to `plan.md`. In short:

**Three layers replace the old stack.** `GameSpec`, `Runner`, `Agent`, `AgentOutput`, `AgentState`, `EpisodeRecorder` and `CheckpointStore` are gone.

| Layer | Job |
|---|---|
| `GameEnv` | Rules and state only. Every setting (seed included) lives in `game_config`. It never sees talk. `get_state()` always reports `done` and `rewards`. |
| `Policy` | Turns what one seat sees into a plain answer (`{"option": 3}`) and optional talk. `ScriptedPolicy` plays seeded rules; `Player` asks a model and reads `<thinking>` / `<answer>`. |
| `ConversationGame` | Runs each phase: talk first, then answers, which it turns into the game's `Action`. Handles retries (with the rejection reason), fallbacks and forced moves. Keeps one `ConversationRecord` of everything, with thinking kept private. |

**Saving is simple and safe.** Each piece saves itself: the env and policies as pickles (a `Player` without its model, re-attached with `set_model`), the record as JSON, all in one run folder written after every step. Loading refuses a different `game_config` and detects a half-written save.

**How the review's findings were addressed:**

| Finding | Now |
|---|---|
| Bug 1: typed actions became dicts in `SIMULTANEOUS` | Fixed. Actions stay typed in memory; regression test added. |
| Bug 2: resume silently changed the game | Fixed. Resume rebuilds the env from the saved `game_config`, and a mismatch is an error. |
| Bug 3: resume overwrote the caller's budget | Fixed in the example script: budget flags given on resume replace the saved limits. |
| Bug 4: checkpoints grew quadratically | Fixed. No growing JSON snapshot; the unused per-agent observation memory is gone. |
| No reconstructable config (6.1) | `game_config` holds every setting and is saved in `game.json`. |
| Runner doing five jobs, string coupling (6.2, 6.3) | `ConversationGame` owns scheduling and the record; forced moves and fallbacks are explicit `source` values. |
| Coup property shims, duplicated RNG (6.4) | Removed. One RNG lives in `CoupState`. |
| Write-only agent memory (6.5) | Removed. Each policy saves exactly its own state. |

**Behaviour is unchanged.** 300 seeded games (random and heuristic, 2 to 6 players) produce the same public history, talk and winners as before, and the seed 0 demo trace is identical. Tests: 164 passed and 1 skipped without the `llm` extra, 165 with it.

**Still open:** a runner for many games (batch, tournament, parallel), validating the new `Player` prompt on a real model, and rewriting the three long-form docs that are now marked out of date.

---

## 1. Verdict

The **decision-point model is strong.** `Interaction` (a generic `mode` plus a game-specific `phase`) and the rule that the environment is the source of truth are the right foundations for many games. Most frameworks never get this part right. Coup is implemented carefully on top of it.

The **lifecycle layer is weak**, and that layer is exactly what the goal asks for. Initialization, configuration, checkpointing, logging and multi-episode running are spread across the `Runner`, the env, the agents and a Coup-specific example script. Each holds part of the picture and nobody holds all of it. Three symptoms follow from that:

1. **No reconstructable episode config.** A run cannot be rebuilt from its own log or checkpoint. Resume silently changes the game (Bug 2), and the example script has to guess CLI flags back out of `agent.describe()`.
2. **Checkpointing is bolted onto the hot path.** A full JSON snapshot is rewritten after every accepted step and grows without limit (Bug 4).
3. **Nothing runs "many games".** The only entry point plays one Coup episode. There is no batch or tournament runner, no run directory layout, no parallelism, and no aggregation.

In short, the inner loop (one decision) is close to right, while the outer loops (one episode, many episodes) still need to be built. Section 6 sketches what that should look like.

---

## 2. Mental model: how it works

### Layers

```
games/<name>/       Rules, state, typed actions, prompt text, scripted policy   (game-specific)
     |  GameSpec (make_env, rules_text, render_observation, scripted_policy)
core/               GameEnv ABC, Interaction, Runner, Scheduler, types           (game-agnostic)
agents/             Agent ABC + AgentState; Scripted, Random, LLM                (game-agnostic)
inference/          InferenceBackend (Mock, OpenAI-compatible: OpenRouter, vLLM), UsageTracker
episodes/           EpisodeRecorder (research JSON), CheckpointStore (recovery), TracePrinter
examples/run_coup.py   The only real entry point: CLI, wiring, resume
```

### One decision (the inner loop)

```
env.current_interaction()  ->  Interaction(id, phase, mode, eligible_players, message_policy)
Runner picks a pattern by mode:
   SINGLE / RESPONSE_WINDOW / DISCUSSION  ->  _run_sequential  (ask in scheduler order until the env closes it)
   SIMULTANEOUS                           ->  _run_simultaneous (ask everyone first, then step each)
For each asked player:
   obs   = env.observe(player)          (filtered view)
   legal = env.legal_actions(player)
   if len(legal)==1 -> auto move, no agent call (ADR-12)
   out   = agent.act(obs, interaction, legal, feedback)
   res   = env.step(player, out)        -> accepted / error + public_events
   rejected? retry with feedback up to max_retries, then fall back to legal[0]
   _record(): step count, recorder.record_step, checkpoint.save_runtime, on_event
```

`interaction_id` is how the Runner notices that the env closed a window early (for example, someone challenged). This is simple, robust and game-agnostic. Keep it.

### Coup as a state machine

`CoupEnv` models a turn as explicit phases (`action -> challenge_action -> block_action -> challenge_block -> resolution`), with `lose_influence` and `exchange` as interrupting phases. A `loss_queue` plus a `continuation` string (`"block_stands"`, `"end_turn"`, ...) lets the turn pause for a card reveal and then resume. This works, it is serializable, and it is the right pattern for interrupt-heavy games.

---

## 3. Design decisions: keep, change, rethink

### Keep (these are good)

| Decision | Why it is right |
|---|---|
| `mode` (generic) vs `phase` (game-specific) | The Runner schedules on 4 modes and never learns any game's rules. This is the core of game flexibility. |
| Env never calls a model or picks who goes first | It keeps envs testable and deterministic, and makes the turn-order policy an experimental variable (`Scheduler`). |
| `observe()` vs `full_state()`, with tests that check what is hidden | Leaking hidden state would invalidate experiments, and this enforces the boundary. |
| `message` and `action` kept separate | Lets you study what agents say against what they do. |
| LLM replies with the *number* of a legal action | This is the most robust protocol for small models, and it keeps "invented action" failures out of the env. |
| Forced moves skip the agent | Saves calls in every game for free. |
| Atomic checkpoint write (`mkstemp` + `fsync` + `os.replace`) | Correct crash safety. |
| Resume-equivalence test (`test_interrupted_resume_matches_uninterrupted_trajectory`) | It is the right kind of test. It needs to be extended (Bug 2, Bug 3). |

### Change

| Decision | Problem | Direction |
|---|---|---|
| `GameSpec.make_env: Callable[..., GameEnv]` with free kwargs | Env construction args are not recorded anywhere reconstructable. `env.config()` is a lossy summary (`"fixed_initial_hands": true`, not the hands). | Store an explicit, serializable env config. See Section 6. |
| Actions are `Action \| Mapping \| None` | Actions turn into dicts at the checkpoint boundary and never turn back, because core has no way to parse a dict back into a game's action. Every env is forced to accept both forms. | Add `GameSpec.parse_action(dict) -> Action`. Keep typed actions in memory and use dicts only on disk. |
| Fallback is "the first legal action" (documented convention) | It is an implicit contract every new game must remember. | Make it explicit with `GameEnv.default_action(*, player_id)` that defaults to `legal[0]`. |
| Optional env methods with silent defaults (`public_state() -> {}`, `public_history() -> []`) or late `NotImplementedError` (`state_dict`) | A new game "works" until the first accepted step with a checkpoint store, then crashes mid-run. | Make them abstract, or check capabilities when the run starts. |
| Each game re-implements `_emit`, `_events`, `_history` | Both Coup and the fixture hand-roll the same public-event buffer. | Provide a small `PublicLog` helper in core that envs compose. |

### Rethink

- **ADR-18 (`AgentState` stores every observation).** Nothing reads it. `LLMAgent` builds each prompt from the current observation only, and `ScriptedAgent` and `RandomAgent` ignore it too. It is write-only memory that dominates checkpoint size (Bug 4). Either make it the agent's real memory (for example, conversation history for the LLM) or keep only what an agent needs to resume (RNG state, remaining script, parse problem).
- **ADR-17 (checkpoint embeds a full copy of the episode record).** Combined with a rewrite on every step, IO grows quadratically. An append-only event log plus a small state snapshot gives the same recovery at linear cost.
- **ADR-08 (one JSON file per episode, written at the end).** It is fine for reading, but if the process crashes you get no log, only a checkpoint. Write JSONL events as you go, then compact them into the final JSON when the episode finishes.

---

## 4. Features against your goal

| Goal capability | Status | Notes |
|---|---|---|
| Emulate many game structures | **Good** | 4 interaction modes. `DISCUSSION` and `SIMULTANEOUS` are proven only by a test fixture, and `SIMULTANEOUS` has a real bug (Bug 1). |
| Add a new game cleanly | **Fair** | One `GameSpec` entry. However, games must hand-roll event logs, accept dict actions, and know the `legal[0]` convention. |
| Play **many** games | **Missing** | There is no batch, sweep, tournament or seat rotation, no parallelism, and no results aggregation. The CLI hardcodes `get_game("coup")`. |
| Initialization / config | **Weak** | There is no single config object. Agents are built before the env knows its player ids (so the example hardcodes `p{i}`). Seeds for env and agents are derived ad hoc in the example. |
| Checkpointing | **Partial** | It works for the default Coup setup, but it is O(n²) (Bug 4), loses env config on resume (Bug 2), overwrites budgets (Bug 3), and breaks typed actions in `SIMULTANEOUS` (Bug 1). |
| Logging | **Fair** | The research JSON is clear and well separated from god view. It is written only at the end (crash = no log), the save is not atomic, and the class has two names (`EpisodeLogger`/`EpisodeRecorder`). |
| Inference backends | **Good** | Small and correct. Some cleanup is listed in Section 5.6. |
| Usage budgets | **Partial** | Per episode only. A sweep needs a budget that spans episodes. |
| Determinism | **Good** for scripted and random | Mock LLM replies are not checkpointed, so a resumed mock run is not bit-identical. |

---

## 5. Bugs

### Bug 1: `SIMULTANEOUS` turns typed actions into dicts on retry and fallback (confirmed, crashes)

`core/runner.py:143-167`. The pending entries store `legal` as `action_to_dict(...)` and rebuild the first output with `AgentOutput(**entry["output"])`. Every retry and every fallback then hands the agent and the env **dicts** instead of the game's typed actions.

Probe: give the fixture typed `Vote` actions and have one agent return one invalid output. The retry receives `legal_actions` of type `dict`, the fallback submits a dict, the env compares it against typed actions, and the run raises `RuntimeError: fallback action rejected`.

The tests do not catch this, for two reasons. The fixture already uses dict actions, and `CoupEnv.validate_action` accepts both forms. Coup never uses `SIMULTANEOUS`, but the first real game that does (Sheriff loading, Werewolf votes) will hit this. Any policy that reads `action.type` will also break.

**Fix:** keep `Action` objects in memory during the interaction. Serialize them only inside `save_runtime`, and rehydrate on load through a `GameSpec.parse_action` (see Section 3).

### Bug 2: resume silently changes the game (confirmed)

Constructor arguments (`max_turns`, `names`, `initial_hands`, `initial_coins`) live on the `CoupEnv` instance, not in `CoupState`. `load_state_dict` restores state but not config. `examples/run_coup.py:170` rebuilds the env as `make_env(num_players=args.players)` on resume.

Probe: start with `max_turns=2`, interrupt, then resume the way the example script does. The uninterrupted game ends with `turn_limit`. The resumed game plays on to turn 14 and ends with a winner.

**Fix:** put the full, reconstructable env config in the checkpoint and rebuild the env from it (Section 6). A cheaper interim fix is to store `max_turns` in `CoupState`.

### Bug 3: resume overwrites the caller's usage budget (confirmed, costs money)

`CheckpointStore.restore_runtime` calls `usage.load_state_dict(...)`, which also restores `limits`. If the original run had no limits, a resume with `--max-calls 999` ends up with `limits=None`, which is an unbounded spend on a paid API. The reverse is also true: you cannot raise a budget on resume.

**Fix:** restore counters only. Limits are always the current caller's decision.

### Bug 4: checkpoint IO grows quadratically (confirmed)

Every accepted step rewrites one JSON file that contains the full episode record, every observation each agent ever saw (each with the full public history, since nothing trims it), and all RNG states. It is pretty-printed with `indent=2`, so each RNG integer takes its own line.

Measured on a 4-player scripted game: **80 writes, 86 KB to 660 KB per file, 26 MB written in total**, compared with a 110 KB episode log. With LLM agents and long games this costs real time and disk, and on networked storage (CARC) it will dominate run time.

**Fix:** use an append-only JSONL event log plus a small snapshot (env state, agent resume state, runner position). Write compact JSON, and checkpoint every N steps or at turn boundaries.

### Smaller bugs (confirmed by reading)

- **The step limit drops the step that tripped it.** `Runner._record` raises on `max_steps` *after* `env.step` already applied the action, so that step is in the env but not in the log or checkpoint.
- **Trace on resume shows player ids, not names.** The `reset` event is only emitted on a fresh start, so after resume `TracePrinter` has no name map.
- **`TracePrinter` is not game-agnostic.** It special-cases lines that start with `"Turn "`, which is Coup's text format.
- **`GenerationConfig.reasoning` does nothing to the request.** It only hides `raw_model_output`. The name suggests it enables reasoning.
- **`cost_usd` is never filled in** by the OpenAI-compatible backend, so the usage total for cost is always `None`.
- **`inference/__init__.py` claims "the deterministic framework never imports this package"**, but `core/runner.py` and `episodes/checkpoint.py` import `inference.usage`.
- **The episode log save is not atomic** (`Path.write_text`), unlike the checkpoint save.
- **Odd error text.** `CoupEnv.validate_action` labels a non-dict, non-action value as `"no action given: ..."`.

---

## 6. Code smells and pattern-level cleanup

This is ordered by impact on your goal.

### 6.1 No episode config object (root cause of the resume and initialization problems)

Today, what an episode *is* gets scattered across six places: env kwargs, `env.config()` (lossy), `runner.config()`, `agent.describe()` (descriptive, not constructive), the CLI `args`, and the seed passed to `run()`. `examples/run_coup.py:126 apply_resume_config` exists only to reverse-engineer CLI flags from `describe()` output, and it refuses mixed agent types.

**Pattern:** one serializable, constructive config.

```python
@dataclass(frozen=True)
class AgentConfig:
    kind: str                      # "scripted" | "random" | "llm"
    params: dict[str, Any]         # policy name, model, backend, GenerationConfig fields...

@dataclass(frozen=True)
class EpisodeConfig:
    game: str
    env: dict[str, Any]            # exact make_env kwargs, so the env can be rebuilt
    seats: dict[str, AgentConfig]  # per seat, mixed types allowed
    runner: RunnerConfig
    seed: int

def build(config: EpisodeConfig) -> tuple[GameEnv, dict[str, Agent], Runner]: ...
```

Store it verbatim at the top of both the log and the checkpoint. Resume becomes `load -> build(config) -> restore state`, with no guessing. A sweep becomes a list of `EpisodeConfig`s. Per-seat agent seeds come from one helper (for example `derive_seed(episode_seed, seat)`) instead of `args.seed * 100 + i` in a script.

It also fixes the chicken-and-egg problem: `seats` is keyed by player id, so the env should expose player ids from config (or `GameSpec.player_ids(env_config)`) before `reset`.

### 6.2 The Runner does five jobs and keeps per-run state on `self`

`Runner.run` stores `self._env`, `self._agents`, `self._logger`, `self._steps` and other fields on the instance. A Runner is therefore single-use at a time and cannot be shared across threads or concurrent episodes. `_record` does step counting, the limit check, recording, building the checkpoint config dict, saving the checkpoint, and the event callback.

**Pattern:** split *policy* from *per-episode state*, and turn the side effects into hooks.

```python
class Runner:                        # stateless policy: scheduler, retries, forced-move rule
    def run(self, *, episode: Episode, hooks: Sequence[Hook] = ()) -> GameResult: ...

@dataclass
class Episode:                       # all per-run state; this is what gets checkpointed
    config: EpisodeConfig
    env: GameEnv
    agents: dict[str, Agent]
    steps: int = 0
    pending: PendingSimultaneous | None = None
    usage: UsageTracker = ...

class Hook(Protocol):                # recorder, checkpointer, tracer, usage, metrics
    def on_start(self, episode): ...
    def on_step(self, episode, event: DecisionEvent): ...
    def on_finish(self, episode, result): ...
```

The recorder, checkpointer and trace printer then become interchangeable hooks, and the `Runner` stops importing from `episodes/` and `inference/`. This is not an event bus. It is a plain list of three methods, which fits the CLAUDE.md style rule.

### 6.3 Stringly-typed coupling between layers

- `agent.describe().get("model")` decides whether the budget check runs (`runner.py:185, 215`), and `metadata.get("model")` decides whether usage is recorded. Give `Agent` an explicit `uses_inference: bool`, or have the LLM agent report usage directly to the tracker.
- `DecisionEvent.to_dict()` reads `metadata["auto"]` and `metadata["fallback"]`. These are framework facts, so make them real fields (`source: Literal["agent","auto","fallback"]`).
- In `CoupEnv`, phases are compared as raw strings (`self._phase == "action"`) even though `CoupPhase` exists, and the continuation is a method-name string looked up in a dict. A `CoupContinuation` StrEnum keeps it serializable and makes it checkable.

### 6.4 `CoupEnv` has 15 property shims over `self.state`

`games/coup/env.py:84-179` is about 95 lines of `@property _players`, `_deck`, `_phase`, ... that forward to `self.state.*`. This is a half-finished migration from loose fields to `CoupState`. Replace them with `s = self.state` at the top of each method and delete the shims. RNG state is also duplicated: `self._rng` plus `state.rng_state`, synced manually in three places. Keep only one (store `random.Random` in the state and serialize it in `to_dict`).

This file is the template every future game author will copy, so cleaning it pays off with each new game.

### 6.5 Agent memory is write-only

`Agent.record_attempt` appends every observation, message, action and feedback, but nothing reads any of it. Decide what agent memory is for:

- If it is meant to be the agent's context, `LLMAgent` should build its prompt from it (multi-turn chat), and observations should stop carrying the full public history.
- If it is only for resume, it should contain only resume-critical fields.

Today it is the largest cost in every checkpoint and does nothing.

### 6.6 Inference layer: duplicated parameters

- `InferenceBackend.generate(...)` takes `max_tokens, temperature, top_p, top_k, json_schema` as separate arguments, repeated in three classes, even though `GenerationConfig` exists. Pass `config: GenerationConfig`.
- The `LLMAgent.__init__` accepts `max_tokens`, `temperature`, `generation_config` *and* `structured_output`, then reconciles them by hand (`llm_agent.py:65-78`). Accept one `GenerationConfig` instead.
- `InferenceBackend` should be an `ABC` like `GameEnv` and `Agent`.
- `UsageTracker` belongs to the episode, not to `inference/`. Move it to `core/` or `episodes/`, which also makes the "never imports inference" claim true.

### 6.7 Small duplication and naming

- `_tuples()` (RNG state JSON round-trip) is duplicated in `agents/scripted.py` and `games/coup/state.py`. Put one `rng_state_to_json` / `rng_state_from_json` pair in core.
- `EpisodeLogger = EpisodeRecorder` alias, plus a `Runner.run(logger=...)` parameter typed as a recorder. Pick one name.
- `ScriptedAgent` and `RandomAgent` duplicate RNG checkpoint code. A small `SeededAgent` base class removes it.

### 6.8 Documentation sprawl

There are 13 docs (about 1,700 lines) for about 2,800 lines of source. `architecture.md`, `design-overview.md`, `repo-walkthrough.md`, `meeting-demo.md` and `design-decisions.md` overlap heavily, and progress claims drift (for example, 135 vs 134 tests). Consolidate to README (quickstart), `architecture.md` (one canonical description), ADRs, per-game rules files, and `progress.md`. The 3,188-line `examples/output/coup-seed0-3p.json` is a generated artifact. Regenerate it in a test, or keep only a short excerpt.

---

## 7. Suggested plan

Each step stands alone, is testable, and moves toward "many games, clean process".

1. **Fix the confirmed bugs, with regression tests.**
   a. Bug 1: keep typed actions in pending simultaneous entries, and add `GameSpec.parse_action` for rehydration on resume. Test: a typed-action fixture plus a forced retry in `SIMULTANEOUS`.
   b. Bug 3: do not restore `limits` from a checkpoint.
   c. Bug 2: store `max_turns` in `CoupState` now. The real fix is step 2.
2. **Introduce `EpisodeConfig` and `build()`.** Write it into the log and the checkpoint. Rewrite resume to use it and delete `apply_resume_config`. Extend the resume-equivalence test to a non-default env config and mixed agent types.
3. **Split `Runner` into a stateless policy plus an `Episode` and hooks** (Section 6.2). Move the recorder, checkpointer and tracer to hooks, and move `UsageTracker` out of `inference/`.
4. **Rework persistence.** Write the JSONL event stream as you go, plus a small snapshot every N steps. Compact to the final JSON at finish. Trim `AgentState` to what resume needs (Section 6.5).
5. **Add a `run_many` / sweep entry point.** Take a list of `EpisodeConfig` (seat rotation and seed ranges as helpers), use one run directory per sweep (`runs/<sweep>/<episode_id>/{config.json, events.jsonl, checkpoint.json, episode.json}`), add a cross-episode budget, skip-if-done for idempotent restarts, and a process pool for parallel episodes. Make the CLI generic (`--game`) instead of `run_coup.py`.
6. **Clean up `CoupEnv`** (Section 6.4) before game 2 copies its pattern. Add `PublicLog` and `default_action` to core, and make checkpoint methods required.
7. **Then build game 2.** The roadmap's own success test ("needs no changes to Runner, agents or logger") becomes realistic after steps 1 to 6.
