# Meeting demo

A script for explaining the project in 5 minutes. Simple English first, then Japanese.

## A. 30-second explanation

> I built the first version of a shared framework for multi-agent self-play in social games. I implemented one real game, Coup, end-to-end, but the framework is not specific to Coup. The key idea is that the environment always says what kind of interaction is happening right now: one player acting, a response window where others can challenge, a discussion, or simultaneous moves. The runner then handles that pattern. Everything runs and is tested without any model, and LLM agents can be plugged in through OpenRouter or vLLM.

## B. 2-minute explanation

> **Goal.** The goal of this first milestone was a small but solid base: one real game working, a framework that is not tied to it, and logs we can analyse later.
>
> **Problem.** Social games differ in their rules, but also in who can act and when. In Coup, after Alice claims the Duke, Bob and Carol may both challenge, and the first challenge decides it. In Deception, people discuss freely. In Sheriff, merchants load their bags at the same time. A simple "current player" loop cannot express these patterns.
>
> **Design.** So every decision point is an *Interaction*. It has a phase, which is game-specific, a mode, which is one of four general patterns, and the list of players who may act. The environment is the source of truth: it holds the hidden state, checks legality, and never calls a model. The runner decides who to ask first and handles invalid answers, and it contains no game rules. Agents see only their own player's observation, and they return a message and a structured action separately.
>
> **Coup.** Coup has explicit phases: the action, a challenge window, a block window, a window to challenge the block, and the resolution. I checked the rules against two rulebook transcriptions and wrote down where we had to interpret. There are 123 tests, including 500 random games that check invariants after every step.
>
> **Next.** Discussion and simultaneous moves already work in the runner, but they are only tested with a small fixture. The next step would be a second real game with a different structure, Sheriff or Deception, and then running real models.

## C. 日本語での説明（やさしい日本語）

**何を作っているか**
- 複数の AI（LLM）がゲームで対戦するための「共通の土台」を作っています。
- まず本物のゲームを 1 つ（Coup）、最初から最後まで動かしました。
- でも土台は Coup 専用ではありません。ほかのゲームも同じ土台に乗せられます。

**一番大事なアイデア**
- ゲームによって「だれが、いつ動けるか」がちがいます。
  - 1 人だけが動く（ふつうの手番）
  - だれかの行動に、ほかの人が反応できる（Coup の「チャレンジ」）
  - みんなで話し合う（Deception）
  - みんなが同時に決める（投票など）
- そこで、ゲーム（Environment）が毎回「今はこのパターンで、動けるのはこの人たち」とはっきり伝えます。
- 進行役（Runner）は、それを見て「だれから先に聞くか」を決めます。進行役はルールを知りません。

**役割の分け方**
- Environment：ルールと本当の状態（かくれたカードも）を持つ。AI は呼ばない。
- Runner：聞く順番と、まちがった答えへの対応。
- Agent：自分のプレイヤーに見えることだけを見て答える。
- 発言（message）と行動（action）は別々に記録する。だから、うそをついたかどうかを後で調べられる。

**今できること、まだ設計だけのこと**
- できる：Coup を最後まで遊べる。テストは 123 個。1 ゲームごとに JSON ログ。モデルなしで全部動く。
- テストだけ：話し合い（DISCUSSION）と同時の手番（SIMULTANEOUS）。小さなテスト用ゲームで確認した。
- 設計だけ：Sheriff、Deception、Pit、本物の LLM での実験、RL。

**次にやること**
- Coup とちがう形のゲームを 1 つ追加する（Sheriff か Deception）。
- 本物のモデル（OpenRouter、または CARC の vLLM）で動かす。

## D. Architecture in plain English

| Part | One sentence |
|---|---|
| **Environment** | The game itself. It knows the real state, including hidden cards, checks whether a move is legal, and applies it. It never talks to a model. |
| **Interaction** | A short description of the current moment: which rule we are in (phase), which pattern (mode), and who may act. |
| **Runner** | The moderator. It reads the interaction, decides who to ask first, passes the answer to the environment, and retries if the answer is invalid. It knows no game rules. |
| **Agent** | A player. It sees only what its player may see and returns a message, an action, or both. It can be scripted, random, or an LLM. |
| **Inference backend** | How an LLM agent reaches a model: a mock for tests, OpenRouter for hosted models, or a vLLM server on CARC. |
| **Episode logger** | Writes one JSON file per game: every decision, what the player saw, what they said and did, and the result. |

## E. Coup demo walkthrough

**Step 1 (optional, 10 seconds)**

```bash
uv run pytest
```

Point at: `122 passed, 1 skipped` (the skipped test needs the optional LLM package). Say: "Everything is tested without any model, API key or GPU."

**Step 2: run one game**

```bash
uv run python examples/run_coup.py
```

Say: "Three scripted players, seed 0. The same seed always gives the same game."

Point at, in order:

1. **Turn 1.** "Carol claims the Duke. This opens a response window: Alice and Bob may respond. The runner asks Alice first; she passes. Bob challenges. Carol really has the Duke, so Bob loses a card and Carol draws a new one."
2. **Turn 2.** "Alice tries to steal from Carol. Only Carol, the target, may block. She claims the Ambassador. Then everyone else may challenge the block. Nobody does, so the block stands. That is four phases in one turn."
3. **Turn 3.** "Foreign Aid. Here the block window is open to every other player, not only a target."
4. **Turn 4.** "Carol tries to assassinate Alice. Alice challenges and loses a card. Then Alice bluffs the Contessa. Bob challenges, because he can see that all three Contessas are already accounted for. Alice is out."
5. **The end.** "Carol wins after 14 turns. 33 agent decisions; 3 forced moves were applied without asking the agent."

**Step 3: open the JSON** (`examples/output/coup-seed0-3p.json`)

- Top of the file: `schema_version`, `seed`, `players[].agent`. Say: "For LLM agents, the model and backend are recorded here."
- `events[16]`:

```json
"interaction": {"phase": "block_action", "mode": "response_window", "eligible_players": ["p0"]},
"player_observation": {"your_cards": ["captain"], "...": "..."},
"output": {
  "message": "I have the Contessa.",
  "action": {"type": "block", "claim": "contessa"}
}
```

Say: "Alice says she has the Contessa, and her action claims it, but her own observation shows she only has a Captain. Because the message, the action and the observation are logged separately, we can measure bluffing directly."

- `events[17]`: Bob's challenge, with the message "All three of those are already accounted for."
- `result`: `winners`, `payoffs`, `num_agent_calls`, `num_invalid_outputs`.

**Optional extras**

```bash
uv run python examples/run_coup.py --quiet --full-state    # adds the hidden god view after every event
uv run python examples/run_coup.py --quiet --agents llm --backend mock    # the whole LLM path, offline
```

## F. Why Coup first?

> Because it is more than taking turns. One action can open three response windows, anyone can challenge, a block can be challenged too, and a player can lose two cards in one turn. It has hidden information, bluffing and elimination, but the rules are short and clear. If the framework handles Coup, it handles the hardest part of turn structure that many social games share.

## G. Why not just `current_player`?

> Because in a response window there is no single current player. After a claim, two or three players may challenge, and the first one decides. A `current_player` field would force us to hard-code an order inside the game. With an Interaction, the game says who *may* act, and the order becomes a setting we can change.

## H. Why are Environment and Runner separate?

> The environment answers "who may act, and what is legal". The runner answers "who do we ask first". In Coup, asking Bob before Carol can change who challenges, so the order is an experimental choice, not a rule. Keeping it in the runner means we can change it, or randomise it, without touching game code. I have a test that runs the same game in reverse order and gets a different challenger.

## I. Why are message and action separate?

> Because saying and doing are different, and that difference is often what we want to study. "It's just four apples, let me through" is a message; declaring four apples is an action. The environment checks only the action. The message is public talk. In the log we can compare what a player said, what they did, and what they really had.

## J. How would Sheriff fit?

> Loading bags is simultaneous: every merchant decides without seeing the others. Declarations are single actions, one merchant at a time. The bribe talk between the Sheriff and one merchant is a discussion with two eligible players. Inspect or pass is a single action. All four modes already exist. The new work would be inside the game, mainly offers of coins and goods next to free talk.

## K. How would Deception fit?

> The forensic scientist places markers but may not speak, so that player only gets single actions with no message allowed. The investigators then discuss, which is the discussion mode, and each can accuse once. The answer is objectively right or wrong, which makes evaluation easy.

## L. How would Pit fit?

> Pit is simultaneous trading. We would turn the real-time shouting into rounds: every player offers some cards at the same time, and the environment matches equal offers. That is the simultaneous mode. It simplifies the real-time part of the physical game.

## M. Where would RL connect later?

> Outside the environment. Every game already produces a JSON file with each observation, output and result. Later we would convert those episodes into training trajectories, for example for prime-rl. The environment interface stays the same. RL consumes episodes; it is not part of the game.

## N. What works now vs what is only designed?

| Works now | Test-only | Designed only |
|---|---|---|
| Coup, 2 to 6 players, all actions, challenges, blocks, elimination | `DISCUSSION` (fixture) | Sheriff, Deception, Pit, communication games |
| `SINGLE`, `RESPONSE_WINDOW` | `SIMULTANEOUS` (fixture) | Real-model experiments |
| Scripted and random agents | | Private or team channels |
| LLM agent with the mock backend | OpenRouter and vLLM clients (tested against a fake local server, never against a real model) | RL integration |
| JSON logs, trace, deterministic seeds | | CARC setup (documented, not yet run) |

Careful wording in the meeting:
- Say "the LLM path is built and tested with a mock", not "LLMs play Coup".
- Say "Sheriff would fit like this", not "Sheriff works".
- Say "CARC setup is documented", not "CARC is set up".

## O. Likely questions from Dhananjay

**Did you use GameBoyWorlds or ProjectStarter?**
> I read them for ideas, like the game registry and how inference is wrapped, but I didn't copy any code. This project needs multi-agent response windows, which a single-agent step loop can't express. If you'd like me to reuse ProjectStarter's inference utilities for consistency, that's a small change.

**Have you run a real LLM yet?**
> Not yet. The LLM path is built and tested with a mock model, including the prompt, the parsing and the retries. Running real models through OpenRouter is the next step. I'd like to agree on which models first.

**What happens when a model outputs something invalid?**
> The environment rejects it with a reason. The runner sends the reason back to the agent and retries, twice by default, then falls back to the safest legal action, such as pass. Every attempt is logged, so the invalid-output rate is a metric.

**How many model calls does one game take?**
> With scripted agents, a 3-player game has about 46 decisions at the median and a 6-player game about 150. Real models will differ. Response windows are the main cost, because every claim asks each other player. Forced moves don't call the model.

**Who answers first in a response window? Isn't that unfair?**
> It's a runner setting. The default is clockwise from the actor. We can randomise it, and we should measure whether it matters.

**Can an agent see hidden information by accident?**
> Prompts are built only from the player's observation. A test checks that two games that differ only in other players' cards produce exactly the same prompt.

**Can players talk freely in Coup?**
> They can say something with every decision, including a pass. There is no free chat outside decisions yet. For games where talk is central, the discussion mode handles it.

**Does it run on CARC?**
> Not verified yet. I documented the setup from CARC's official guides. One finding: CARC blocks VS Code Remote-SSH on login nodes and asks people to run coding agents on compute nodes, so I'll develop on a CPU compute node. I need to know which project account to use.

**What would be the next game?**
> Sheriff or Deception, because each uses a different interaction pattern from Coup. Which one fits the research question better?

## P. 5-minute meeting flow

| Time | What | Show |
|---|---|---|
| 0:00–0:30 | Goal | Section A, out loud |
| 0:30–1:30 | Architecture | README diagram; environment vs runner; the four modes |
| 1:30–3:00 | Demo | `uv run python examples/run_coup.py`; Turns 1, 2 and 4 |
| 3:00–4:00 | JSON and other games | `events[16]` in the JSON; `docs/game-format-matrix.md` (Sheriff, Deception) |
| 4:00–5:00 | Questions and next step | Ask: which second game? which models and budget? |
