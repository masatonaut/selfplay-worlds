# Game format matrix

How candidate games map onto the four interaction modes. Only Coup is implemented. For every other game this is a **design sketch**: its rules must be checked against the published rulebook before implementation, the same way Coup was (`docs/coup-rules.md`).

## Status legend

| Status | Meaning |
|---|---|
| **IMPLEMENTED** | Real game, playable end-to-end, rule tests |
| **TEST-SUPPORTED** | The framework handles the pattern, proven with a small test fixture, but no real game uses it yet |
| **DESIGNED ONLY** | Written down here; no code |

## Summary

| Game | Modes it needs | Language is... | Hidden information | Status |
|---|---|---|---|---|
| Coup | `SINGLE`, `RESPONSE_WINDOW` | optional table talk; the claim is a structured action | own cards, deck | **IMPLEMENTED** |
| Sheriff of Nottingham | `SIMULTANEOUS`, `SINGLE`, `DISCUSSION` | the core: persuasion and bribes | bag contents, hands | DESIGNED ONLY |
| Deception: Murder in Hong Kong | `SINGLE`, `DISCUSSION` | the investigators' main tool; one role may not speak | roles, the solution | DESIGNED ONLY |
| Pit | `SIMULTANEOUS` | minor (numbers) | hands | DESIGNED ONLY |
| Just One | `SIMULTANEOUS`, `SINGLE` | the move itself | the secret word (for the guesser) | DESIGNED ONLY |

| Mode | Status | Where |
|---|---|---|
| `SINGLE` | IMPLEMENTED | Coup |
| `RESPONSE_WINDOW` | IMPLEMENTED | Coup |
| `DISCUSSION` | TEST-SUPPORTED | `tests/fixtures/talk_then_vote.py` |
| `SIMULTANEOUS` | TEST-SUPPORTED | `tests/fixtures/talk_then_vote.py` |

## Coup (IMPLEMENTED)

- **Core interaction:** one player acts; the others may challenge the claim; the target (or anyone, for Foreign Aid) may block; anyone may challenge the block; then the result.
- **Modes:** `SINGLE` for the action, `RESPONSE_WINDOW` for each reaction, `SINGLE` for losing a card and for the Ambassador's exchange.
- **Who acts / who may respond:** the current player acts; all other living players may challenge; blockers depend on the action.
- **Language:** optional talk attached to every decision ("I'm the Duke").
- **Structured action:** everything that changes the game: `{"type": "tax"}`, `{"type": "challenge"}`, `{"type": "block", "claim": "contessa"}`.
- **Hidden information:** each player's cards and the deck order.
- **Outcome:** last player with influence wins (payoff 1 / 0).
- **Implemented:** all of the above, for 2 to 6 players. **Future:** nothing needed for M1.

## Sheriff of Nottingham (DESIGNED ONLY)

- **Core interaction:** merchants secretly load bags, declare their contents (they may lie about the kind of goods), then negotiate with the Sheriff, who inspects or lets each bag pass.
- **Modes:** loading bags `SIMULTANEOUS` → declarations `SINGLE`, one merchant at a time → negotiation `DISCUSSION` between the Sheriff and one merchant → inspect or pass `SINGLE` (the Sheriff).
- **Who acts / who may respond:** each merchant declares; during a negotiation only the Sheriff and that merchant are eligible.
- **Language:** the heart of the game: persuasion, threats, promises.
- **Structured action:** `{"type": "declare", "good": "apple", "count": 4}`, offers of coins or goods, `{"type": "inspect"}` or `{"type": "pass"}`. Example of message versus action: message "It's just four apples. Let me through." with action `{"type": "declare", "good": "apple", "count": 4}`.
- **Hidden information:** bag contents and hands.
- **Outcome:** scores from goods, coins, penalties and bonuses.
- **Framework representation:** the four modes are enough. New work is inside the game: structured offers next to free talk, and deciding which parts of a deal are binding.
- **Future:** candidate for Milestone 2.

## Deception: Murder in Hong Kong (DESIGNED ONLY)

- **Core interaction:** a secret murderer picks a weapon and a clue; the forensic scientist, who knows the answer but may not talk, gives hints by placing markers; the investigators discuss and each may accuse once.
- **Modes:** the murderer's secret choice `SINGLE` → markers `SINGLE`, no message allowed → discussion `DISCUSSION` → accusation `SINGLE` (or an `accuse` action inside the discussion).
- **Who acts / who may respond:** the forensic scientist is never eligible in the discussion; investigators (and the hidden murderer) are.
- **Language:** the investigators' main tool; the murderer tries to mislead.
- **Structured action:** marker placement, `{"type": "accuse", "means": ..., "clue": ...}`.
- **Hidden information:** roles and the solution.
- **Outcome:** objectively checkable: the accusation is right or wrong.
- **Framework representation:** four modes are enough; the silent role is `message_policy=NONE` plus not being eligible in `DISCUSSION`.
- **Future:** candidate for Milestone 2.

## Pit (DESIGNED ONLY)

- **Core interaction:** players trade sets of cards at the same time, trying to collect all cards of one commodity.
- **Modes:** repeated `SIMULTANEOUS` rounds: every player offers a number of cards; the environment matches equal offers.
- **Who acts / who may respond:** everyone, every round.
- **Language:** minor; the physical game is shouting numbers.
- **Structured action:** `{"type": "offer", "count": 2}` and which cards to give.
- **Hidden information:** hands.
- **Outcome:** first player to corner a commodity scores.
- **Framework representation:** `SIMULTANEOUS`. The real-time race of the physical game becomes rounds, which is a simplification.
- **Future:** later milestone.

## Just One (DESIGNED ONLY), a communication game

- **Core interaction:** everyone except the guesser writes a one-word clue in secret; identical clues cancel; the guesser guesses.
- **Modes:** clues `SIMULTANEOUS` with a required message → guess `SINGLE`.
- **Who acts / who may respond:** clue givers, then the guesser.
- **Language:** the message **is** the move.
- **Structured action:** little; the environment validates the message itself (one word, not the secret word).
- **Hidden information:** the secret word, for the guesser.
- **Outcome:** cooperative score.
- **Framework representation:** already possible, because `step` receives the whole `AgentOutput`, message included. Open design choice: clue as `message` or as an action field.
- **Future:** later milestone. A team game such as Trapwords would also need **private team channels**, which the framework does not have yet.

## What the matrix shows

- Coup exercises the part of turn structure most games share: a response window that the first responder closes. That is why it came first.
- Sheriff and Deception fit the four modes without new framework concepts; their new work is inside the game.
- Communication games put the move inside the message, which the current `step` signature already allows.
- The one clear framework gap is **private channels** (team talk, secret side deals). It is not built, because no implemented game needs it yet.
