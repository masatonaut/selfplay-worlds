# Redesign plan: GameEnv, Policy, ConversationGame

Status: built (see `report.md` section 0). One later change: thinking no longer goes through ConversationGame or the record; each Player keeps it (ADR-23 in `docs/design-decisions.md`). It is based on `report.md` and the design discussion that followed it. All open questions have been answered (section 9).

---

## 1. Goal

Replace the current `GameEnv` / `GameSpec` / `Runner` / `Agent` / `EpisodeRecorder` / `CheckpointStore` stack with three clear layers:

| Layer | Owns | Never does |
|---|---|---|
| **GameEnv** | Rules, true state, legality, game history, done and rewards, turning an answer into its own `Action` type | See talk, prompts, models or policies |
| **Policy** (`ScriptedPolicy`, `Player`) | Turning what a seat sees into an answer (and a message) | See hidden state, call the env, or know the game's `Action` class |
| **ConversationGame** | Talk, the order players are asked in, building `Action`s from answers, retries, the conversation record, saving and loading a whole game | Contain game rules |

Every class saves and loads itself. The env, the policies and the record are saved as separate files in one folder.

---

## 2. Decisions taken

| # | Decision |
|---|---|
| D1 | `GameEnv(name, game_config)` stores both and calls `reset()` at the end of `__init__`. `reset()` sets `n_steps = 0`. |
| D2 | `game_config` is the **only** source of game settings, including the seed. Subclasses read every setting from it inside `reset()`. |
| D3 | `GameEnv.save(path)` pickles the env. `GameEnv.load(path)` reads a pickle and raises if the saved `game_config` differs from this instance's in any key or value. |
| D4 | `step` takes a game-specific `Action` object. `Action` is an abstract class that each game implements. |
| D5 | The policy returns a raw **answer** (a plain dict). ConversationGame turns it into the game's `Action` with the game-specific constructor `Action.from_answer(...)`, after the dialogue, then calls `step`. |
| D6 | Legality is checked inside each game. An illegal action changes nothing and comes back as `StepResult(accepted=False, error=<reason>)`, so a retry can tell the policy what went wrong. |
| D7 | The dict returned by `get_state` must include `done` and `rewards`. Nothing else is required. |
| D8 | `get_dialogue_phase()` replaces `current_interaction()`. Splitting it into separate "talk" and "who acts" parts is postponed. |
| D9 | How long talk lasts is part of the dialogue phase the env returns (`talk_rounds`). |
| D10 | `get_observation` includes the game's history and the current menu of options. `ConversationGame.get_conversation()` returns the conversation history. Policies decide on both. |
| D11 | Policies talk through `get_message`. |
| D12 | Policy state is saved separately: `Player` pickles its state **without** its model, and a separate `set_model(...)` makes it whole again. Saves happen only between `ConversationGame.step()` calls. |
| D13 | The default answer is "the number of a listed option". Games may also accept richer answers in `from_answer`. |
| D14 | No `GameSpec`. No prompts or scripted policies anywhere in the env layer. |
| D15 | `GameEnv.step` is concrete: it calls the game's abstract `_step` and increments `n_steps` only when the action is accepted. |
| D16 | Coup's turn phase gets one talk round for the acting player, which keeps today's table talk ("I'm the Duke"). |

---

## 3. Target layout

```
src/selfplay_worlds/
  core/
    env.py            GameEnv, Action, StepResult, DialoguePhase, DialogueMode
    conversation.py   ConversationGame, ConversationRecord
  policies/
    base.py           Policy (+ renderer lookup by game name)
    scripted.py       ScriptedPolicy, RandomPolicy
    player.py         Player (LLM-backed)
  games/
    __init__.py       ENVS = {"coup": CoupEnv}; RENDERERS = {"coup": render_coup}
    coup/
      env.py          CoupEnv(GameEnv)
      actions.py      CoupAction(Action)
      state.py        CoupState (unchanged in spirit)
      prompts.py      RULES_TEXT, render_coup
      policies.py     CoupHeuristicPolicy(ScriptedPolicy)
  inference/          unchanged (backends, GenerationConfig, UsageTracker)
```

Deleted at the end: `core/runner.py`, `core/interaction.py`, `core/types.py` (whatever survives moves into `core/env.py`), `agents/`, `episodes/checkpoint.py`, `episodes/log.py`. The `Scheduler` can stay as a small helper used by ConversationGame.

---

## 4. Class specs

All public functions use keyword-only arguments, per `CLAUDE.md`.

### 4.1 Answers and `Action` (core/env.py)

An **answer** is what a policy returns. It is a plain, game-agnostic dict:

```python
{"option": 3}                       # default: number of a listed option (1-based)
{"type": "steal", "target": "p2"}   # a game may also accept its own richer form
```

```python
class Action(ABC):
    """One game-specific action. Policies never build these; ConversationGame does,
    from a policy's answer, through the game's from_answer."""

    player_id: str

    @classmethod
    @abstractmethod
    def from_answer(cls, *, answer: dict, player_id: str, observation: dict) -> "Action":
        """Turn a policy's answer into this game's Action.
        Raises ValueError(reason) if the answer cannot be read (for example option 9 of 4).
        Reading an answer is not checking legality: env.step does that."""

    @abstractmethod
    def to_dict(self) -> dict: ...      # for the conversation record
```

The env names its action class with a class attribute: `CoupEnv.action_class = CoupAction`.

### 4.2 `DialoguePhase` (core/env.py)

The current four modes are kept for now (D8). `SINGLE` is renamed `ACTION`.

```python
class DialogueMode(StrEnum):
    ACTION = "action"                    # one player acts (optionally talking first)
    RESPONSE_WINDOW = "response_window"  # eligible players respond in order; the env may close it early
    DISCUSSION = "discussion"            # talk rounds for everyone, then the action (if any)
    SIMULTANEOUS = "simultaneous"        # everyone answers before anyone's action is applied

@dataclass(frozen=True)
class DialoguePhase:
    phase_id: int              # increases every time the env opens a new phase; this is how
                               # ConversationGame notices the env closed a window early
    phase: str                 # game-specific name, e.g. "challenge_action"
    mode: DialogueMode
    eligible: tuple[str, ...]  # who may act, in the env's default order
    talk_rounds: int = 0       # D9: talk before acting (0 = straight to the action)
    description: str = ""
```

### 4.3 `StepResult` and `GameEnv` (core/env.py)

```python
@dataclass
class StepResult:
    accepted: bool
    error: str | None = None                                   # why it was rejected (D6)
    public_events: list[str] = field(default_factory=list)


class GameEnv(ABC):
    action_class: type[Action]          # set by each game

    def __init__(self, *, name: str, game_config: dict) -> None:
        self.name = name
        self.game_config = dict(game_config)  # D2: every setting, seed included
        self.reset()

    def reset(self) -> None:
        """Subclasses call super().reset() and then build their state ONLY from
        self.game_config (their own fields do not exist yet when this first runs)."""
        self.n_steps = 0

    @property
    @abstractmethod
    def player_ids(self) -> list[str]: ...

    @abstractmethod
    def get_dialogue_phase(self) -> DialoguePhase | None:
        """The open phase, or None once the game is over."""

    @abstractmethod
    def get_observation(self, *, player_id: str) -> dict:
        """What this player may know, and nothing more. Includes:
            "history": the game's public history
            "options": the menu of choices this player can pick by number right now
                       (a menu for prompts and policies, not a legality guarantee)
        Never hidden state."""

    def step(self, *, player_id: str, action: Action) -> StepResult:
        """D15: concrete. Calls _step and increments n_steps only when accepted."""
        result = self._step(player_id=player_id, action=action)
        if result.accepted:
            self.n_steps += 1
        return result

    @abstractmethod
    def _step(self, *, player_id: str, action: Action) -> StepResult:
        """Apply one action. Legality is checked HERE, by each game.
        If the action is not legal: change nothing and return
        StepResult(accepted=False, error=<why>)."""

    @abstractmethod
    def get_state(self, **kwargs) -> dict:
        """Game state as a dict. kwargs select the view (e.g. view="public" | "full").
        The returned dict MUST include:
            "done":    bool
            "rewards": dict[player_id, float]   (zeros until the game ends)"""

    def save(self, *, path: Path) -> Path: ...   # pickle self
    def load(self, *, path: Path) -> None:
        """Read a pickle. Raise ValueError naming every key that is missing, extra,
        or has a different value compared with self.game_config. Otherwise adopt
        the saved state."""
```

### 4.4 `Policy` (policies/base.py)

```python
class Policy(ABC):
    def __init__(self, *, game_name: str) -> None:
        self.game_name = game_name

    def render_observation(self, *, observation: dict) -> str:
        """Look up RENDERERS[self.game_name]. Falls back to pretty JSON."""

    @abstractmethod
    def get_action(self, *, observation: dict, conversation: list[dict]) -> dict:
        """Return an answer (section 4.1). If observation has "feedback", the previous
        answer was rejected and "feedback" says why."""

    def get_message(self, *, observation: dict, conversation: list[dict]) -> str | None:
        """D11: what to say during talk. Default: say nothing."""
        return None

    def save(self, *, path: Path) -> Path: ...   # pickle
    def load(self, *, path: Path) -> None: ...
```

### 4.5 `ScriptedPolicy` (policies/scripted.py)

```python
class ScriptedPolicy(Policy):
    """Deterministic or seeded rules. Its RNG lives on the instance, so it is pickled with it."""

    def get_action(self, *, observation, conversation):
        return self.step(observation=observation, conversation=conversation)

    @abstractmethod
    def step(self, *, observation: dict, conversation: list[dict]) -> dict: ...
```

`RandomPolicy(ScriptedPolicy)` returns `{"option": rng.randint(1, len(observation["options"]))}`. `CoupHeuristicPolicy` ports today's `heuristic_policy` function and returns Coup-shaped answers or option numbers.

### 4.6 `Player` (policies/player.py)

```python
class Player(Policy):
    def __init__(self, *, game_name: str, model: InferenceBackend, generation_config: GenerationConfig): ...

    def set_model(self, *, model: InferenceBackend) -> None:
        """D12: re-attach a model after load(). Calling get_action without a model raises."""

    def get_action(self, *, observation, conversation):
        rendered = self.render_observation(observation=observation)
        prompt = self.get_prompt(rendered_observation=rendered, observation=observation,
                                 conversation=conversation)
        text = self.model.generate(messages=prompt, ...).text
        blocks = self.parse_response(text=text)          # {"thinking": str | None, "answer": str | None}
        self.last_thinking = blocks["thinking"]          # ConversationGame records it as private
        return self.parse_answer(answer=blocks["answer"], observation=observation)

    def get_message(self, *, observation, conversation): ...   # same pipeline, asks for talk only

    def get_prompt(self, *, rendered_observation, observation, conversation) -> list[dict]: ...
    def parse_response(self, *, text: str) -> dict: ...
        # reads <thinking>...</thinking><answer>...</answer>; tolerant of missing thinking
    def parse_answer(self, *, answer: str | None, observation: dict) -> dict:
        # turns the answer block into an answer dict; default reads a JSON object or a bare
        # option number (D13). Unreadable text -> {} so from_answer rejects it with a reason.

    def __getstate__(self):     # D12: pickle everything except self.model
        ...
```

`Player` keeps its own memory (past prompts and replies, if any) and its usage counters on the instance, so both survive save/load. Parsing is in two stages: the Player turns model text into an answer dict, then the game's `from_answer` turns the dict into an `Action`. Game-specific parsing therefore lives with the game, not in `Player`.

### 4.7 `ConversationRecord` (core/conversation.py)

One chronological JSON list, covering every mode:

```json
{"index": 12, "n_steps": 7, "phase_id": 5, "phase": "challenge_action", "mode": "response_window",
 "player_id": "p2", "kind": "message | thinking | action | event",
 "content": "...", "visibility": "public | private",
 "accepted": true, "error": null, "attempt": 1}
```

- `message`: talk (public).
- `thinking`: a Player's thinking block (private to its author).
- `action`: every attempt, accepted or not, with the raw answer and, when readable, `action.to_dict()`.
- `event`: the public events the env returned from `step`.

Methods: `append(...)`, `visible_to(*, player_id)`, `save(*, path)` (atomic JSON write), `load(*, path)`.

### 4.8 `ConversationGame` (core/conversation.py)

```python
class ConversationGame:
    def __init__(self, *, env: GameEnv, players: dict[str, Policy], max_retries: int = 2): ...
        # raises if players do not exactly match env.player_ids

    def get_conversation(self, *, player_id: str) -> list[dict]:
        return self.record.visible_to(player_id=player_id)

    def step(self) -> None: ...        # one dialogue phase (section 5)
    def run(self) -> dict:             # step until get_dialogue_phase() is None; return env.get_state()

    def save(self, *, folder: Path) -> None: ...
    def load(self, *, folder: Path) -> None: ...
```

---

## 5. `ConversationGame.step()` flow

```
phase = env.get_dialogue_phase()

ACTION:
    pid = phase.eligible[0]
    repeat phase.talk_rounds times: talk(pid)      # Coup's turn phase: 1 round (D16)
    act(pid)

DISCUSSION:
    repeat phase.talk_rounds times, for pid in scheduler order: talk(pid)
    then, for pid in phase.eligible: act(pid)

RESPONSE_WINDOW:
    for pid in scheduler order:
        stop if env.get_dialogue_phase().phase_id changed   (the env closed the window)
        skip if pid is no longer eligible
        repeat phase.talk_rounds times: talk(pid)
        act(pid)

SIMULTANEOUS:
    collect every eligible player's answer FIRST (nobody sees another's choice)
    then build and step each one, with retries as in act()

talk(pid):
    msg = players[pid].get_message(observation, conversation)  -> record (message), if not None

act(pid):
    observation = env.get_observation(player_id=pid)
    if len(observation["options"]) == 1: answer = {"option": 1}   (forced move, no policy call)
    for attempt in 1..max_retries+1:
        answer = players[pid].get_action(observation, conversation)        # unless forced
        try:   action = env.action_class.from_answer(answer=answer, player_id=pid, observation=observation)
        except ValueError as e: result = StepResult(accepted=False, error=str(e))
        else:  result = env.step(player_id=pid, action=action)
        record the attempt (+ thinking if any, + public events if accepted)
        if result.accepted: return
        observation = {**observation, "feedback": result.error}
    fallback: answer = {"option": 1}; it must be accepted, otherwise raise
```

The forced-move skip, retries and fallback carry over from today's Runner unchanged in behaviour.

---

## 6. Save and load layout

```
<run_folder>/
  game.json          {"game": name, "game_config": {...}, "player_ids": [...],
                      "policies": {pid: class name}, "n_steps": int}
  env.pkl            GameEnv.save
  record.json        ConversationRecord.save
  policies/<pid>.pkl Policy.save (Player without its model)
```

Resume:

```python
env = CoupEnv(game_config=json.load(...)["game_config"])  # config comes from the save, so it matches
env.load(path=folder / "env.pkl")                          # still checked (D3)
players = {...}; for each: p.load(path=...); Player: p.set_model(model=...)
game = ConversationGame(env=env, players=players); game.load(folder=folder); game.run()
```

Saving happens only between `step()` calls, so there is never a half-finished phase to persist. Pickles are only ever loaded from folders this code wrote. Note that renaming a class breaks old pickles. That is acceptable while the code is moving fast.

---

## 7. Coup port: what changes in `CoupEnv`

- The constructor becomes `CoupEnv(*, game_config)` → `super().__init__(name="coup", game_config=...)`. `num_players`, `names`, `initial_hands`, `initial_coins`, `starting_player`, `max_turns` and `seed` are all read from `game_config` in `reset()`.
- Delete the 15 property shims. Use `self.state` directly. Keep a single RNG, inside the state.
- `legal_actions` becomes the source of `observation["options"]` (as dicts). `_step` re-checks legality and returns `StepResult(accepted=False, error=...)` for an illegal action, reusing today's error messages.
- `CoupAction.from_answer` accepts `{"option": n}` (looked up in `observation["options"]`) or a Coup-shaped dict (today's `CoupAction.from_dict`).
- `_step` no longer emits `"Alice says ..."`; talk lives in the record.
- `get_state(view="public" | "full")` replaces `public_state` / `full_state` / `result`, with `done` and `rewards` always present.
- Coup phases map to `DialogueMode`: `action` is `ACTION` with `talk_rounds=1` (D16); `lose_influence` and `exchange` are `ACTION` with `talk_rounds=0`; the three challenge and block windows are `RESPONSE_WINDOW` with `talk_rounds=1` (a responder may say something before passing or challenging, as today).
- The rule tests port with a thin helper change (`act(env, ...)` builds a `CoupAction` and calls `step`). The rules themselves do not change.

---

## 8. Build order

Each phase ends with `uv run pytest` passing. Work on a branch, because the new `core/env.py` replaces the old one by name.

1. **Core abstractions.** `Action`, `StepResult`, `DialoguePhase`, `GameEnv` with the concrete `step`/`_step` split, pickle save/load and the config check. Tests: a config mismatch raises and names the keys; a save/load round trip; `n_steps` counts only accepted steps.
2. **Policies.** `Policy`, `ScriptedPolicy`, `RandomPolicy`, `Player` using `MockBackend`. Tests: thinking/answer parsing, answer parsing (JSON and bare number), a pickle without the model, `set_model` required before `get_action`.
3. **ConversationGame and ConversationRecord.** Port `tests/fixtures/talk_then_vote.py` to the new API. Tests: all four modes, talk rounds, an early-closing response window, simultaneous hiding, `from_answer` errors and illegal actions both retried with their reason, fallback, forced moves, `get_conversation` hides private thinking.
4. **Coup env port** (section 7). Port rule, legality, setup and observation tests. Keep the 500-game stress test.
5. **Coup policies and prompts.** `CoupHeuristicPolicy`, `render_coup`, `RULES_TEXT` registered by game name.
6. **Example and resume.** Rewrite `examples/run_coup.py` on the new API. Tests: seed determinism; interrupted-then-resumed equals uninterrupted, including a non-default `max_turns` (today's Bug 2).
7. **Delete the old stack** (section 3). Update `CLAUDE.md` architecture rules, `docs/architecture.md`, `docs/progress.md`, and mark the superseded ADRs (06, 12, 14, 17, 18) in `docs/design-decisions.md`.

---

## 9. Answered questions

| Question | Answer | Where it lands |
|---|---|---|
| Who builds the `Action`? | The policy returns an answer; ConversationGame builds the game's `Action` from it with `from_answer` | D5, 4.1, 5 |
| Required `get_state` keys | `done` and `rewards` only | D7, 4.3 |
| Do policies get `get_message`? | Yes | D11, 4.4 |
| Coup table talk on your own turn | Keep it: one talk round for the actor | D16, 7 |
| Should a rejected action say why? | Yes: `StepResult(accepted=False, error=...)` | D6, 4.3, 5 |
| Who increments `n_steps`? | The base class, through a concrete `step` around the game's `_step` | D15, 4.3 |

## 10. Out of scope for this plan

- Splitting the dialogue phase into separate "talk" and "who acts" parts (D8, postponed).
- Running many games: a batch or tournament runner, parallel episodes, aggregation (report section 7, step 5).
- Private and team channels beyond "thinking is private".
- Budgets across many episodes (`UsageTracker` stays per `Player` for now).
