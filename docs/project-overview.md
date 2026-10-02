# SelfPlayWorlds project overview

This document explains the project from the beginning. It is for Jonathan, DJ, and other group members who have not followed the earlier design discussion.

## What we are building

SelfPlayWorlds is a reusable framework for games where several LLM agents play against or alongside each other.

The basic loop is:

```text
GAME STATE
→ CURRENT SITUATION
→ WHO ACTS NEXT?
→ AGENT
→ MESSAGE + ACTION
→ CHECK + UPDATE
→ NEW GAME STATE
```

The game owns the rules and the true state. Each agent sees only the information that its player should see. The framework asks the right agent for a decision, checks the decision, updates the game, and records what happened.

## What we learned from game scouting

We looked across 21 games in three broad groups: bluffing and deduction, negotiation, and communication.

The main implementation questions were:

- Who acts next?
- Who can react?
- Does each player act in sequence, or do several players choose at the same time?
- Does the agent choose a structured action, speak freely, or do both?
- Can the result be checked directly from the game rules?

These questions matter more to the framework than the theme of a game.

## Why Coup was first

Coup has a small state and a small list of actions. It includes bluffing, challenges, blocks, and hidden cards. Its results can be checked directly from the rules.

It is more useful than a simple alternating-turn game because one action can open several reactions:

```text
action
→ challenge
→ block
→ challenge block
→ update state
```

This let us test ordinary turns and reaction windows in one compact game.

## The current design

- **GameEnv:** Owns the game rules and the true game state.
- **Interaction:** Describes the decision that is open now and which players may take part.
- **Scheduler:** Chooses the order in which eligible players are asked.
- **Agent / AgentState:** The agent chooses a response, and its state stores what that player has experienced.
- **message + action:** The message is what the agent says, while the action is what it chooses to do.
- **Runner:** Repeats the game loop and connects the environment, scheduler, agents, records, and checkpoints.
- **EpisodeRecorder:** Saves the research record of what happened during an episode.
- **CheckpointStore:** Saves enough runtime state to continue an interrupted episode.
- **UsageTracker:** Counts model calls, tokens, and inference time.

## The whiteboard mapping

| Whiteboard idea | Current code |
|---|---|
| GAME | `GameEnv` |
| Conversation Situation | `Interaction` |
| who may act | Environment |
| who is asked first | `Scheduler` |
| Act / Decision | `Agent` |
| Action Creator | legal actions plus a typed Action |
| `valid(action)` | Environment checks legality |
| what the agent says | message |
| what the agent does | action |
| save / restart | `CheckpointStore` |
| budget | `UsageTracker` |

The environment decides who **may** act because that comes from the game rules. The scheduler decides who is **asked first** when several players may respond.

## What is working now

Coup currently works end to end with:

- 2 to 6 players
- challenges
- blocks
- challenges to blocks
- hidden information
- a different observation for each player
- separate history for each agent
- episode logging
- checkpoint and resume
- model usage tracking

The real-model baseline used:

```text
Qwen/Qwen2.5-7B-Instruct
vLLM
CARC
1 x A40
```

The full three-player episode made 15 real model calls. Challenge, block, and challenge-block phases all occurred. There were 0 invalid outputs, 0 retries, and 0 fallbacks. The checkpoint passed, and the final artifact validation passed.

## Four interaction styles

- **SINGLE:** One player acts.
- **RESPONSE_WINDOW:** Several players may react.
- **DISCUSSION:** Players take turns speaking.
- **SIMULTANEOUS:** Everyone chooses before seeing the others' choices.

`SINGLE` and `RESPONSE_WINDOW` are validated in the real Coup environment. `DISCUSSION` and `SIMULTANEOUS` are implemented and tested with a small fixture only. They have not been validated in a second real game.

## Current Gemma status

The target model is `google/gemma-4-31B-it`. CARC job `12558939` is currently `PENDING (Priority)`, and all visible A100-80GB GPUs were allocated when last checked. This is not a Gemma success result.
