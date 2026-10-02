# Quick design review for DJ

```text
Game State
→ Interaction
→ Scheduler
→ Agent
→ message + action
→ validate + step
→ new Game State
```

| Whiteboard idea | Current code | Plain-English meaning |
|---|---|---|
| GAME | `GameEnv` | Holds the rules and the true game state. |
| Conversation Situation | `Interaction` | Describes the decision that is open now. |
| who may act | Environment | The game rules decide which players are eligible. |
| who is asked first | `Scheduler` | Chooses the order when several players are eligible. |
| Act / Decision | `Agent` | Chooses what one player says and does. |
| Action Creator | `legal_actions()` plus a typed Action | Gives the agent the exact choices that are available now. |
| `valid(action)` | `validate_action()` and `step()` | Checks that the action is legal before changing the game. |
| what the agent says | `message` | Stores the agent's words. |
| what the agent does | `action` | Stores the structured game move. |
| per-player memory | `AgentState` | Stores what that player has seen and tried. |
| save / restart | `CheckpointStore` | Saves enough state to continue later. |
| budget | `UsageTracker` | Counts model calls, tokens, and time. |

The environment owns the real game state. Each agent has a separate history. The episode log records what happened, while the checkpoint stores what is needed to restart safely.

## Review questions

1. Does Interaction match what you meant by Conversation Situation?
2. Is it correct that the Environment says who MAY act, while Scheduler decides who is ASKED first?
3. Is the current Action / valid(action) split what you intended?
4. Is message + action the right separation?
5. Is the split between game state, per-agent state, episode log and checkpoint correct?
