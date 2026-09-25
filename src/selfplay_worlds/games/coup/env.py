"""Coup environment.

Rules: docs/coup-rules.md (verified against two transcriptions of the official
rulebook). One turn is modelled as explicit phases:

    action
      -> challenge_action   (if the action claims a character)
      -> block_action       (if the action can be blocked and survived)
      -> challenge_block    (if someone blocked)
      -> resolution         (automatic, no agent input)

Two more SINGLE phases interrupt a turn when needed:
    lose_influence  (a player must reveal a card)
    exchange        (the Ambassador chooses which cards to keep)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import combinations

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.core.interaction import Interaction, InteractionMode, MessagePolicy
from selfplay_worlds.core.types import Action, AgentOutput, GameResult, StepResult
from selfplay_worlds.games.coup.cards import (
    ACTIONS,
    COUP_COST,
    FORCED_COUP_COINS,
    FULL_DECK,
    Card,
)

DEFAULT_NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
DEFAULT_MAX_TURNS = 100
"""Not a rule of Coup: a safety net so a game between agents that repeat the
same moves (for example two lone Captains stealing from each other and
blocking forever) still ends. See docs/coup-rules.md."""

PHASE_MODES = {
    "action": InteractionMode.SINGLE,
    "challenge_action": InteractionMode.RESPONSE_WINDOW,
    "block_action": InteractionMode.RESPONSE_WINDOW,
    "challenge_block": InteractionMode.RESPONSE_WINDOW,
    "lose_influence": InteractionMode.SINGLE,
    "exchange": InteractionMode.SINGLE,
}


def _coins(n: int) -> str:
    return "1 coin" if n == 1 else f"{n} coins"


@dataclass
class Player:
    id: str
    name: str
    coins: int
    hidden: list[Card]
    revealed: list[Card] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return bool(self.hidden)


@dataclass
class Turn:
    """Facts about the turn in progress."""

    actor: str
    action: str | None = None
    target: str | None = None
    paid: int = 0
    blocker: str | None = None
    block_claim: Card | None = None


class CoupEnv(GameEnv):
    name = "coup"

    def __init__(
        self,
        *,
        num_players: int = 3,
        names: list[str] | None = None,
        initial_hands: dict[str, list[str]] | None = None,
        initial_coins: dict[str, int] | None = None,
        starting_player: str | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        """``initial_hands`` / ``initial_coins`` fix the opening position (tests and demos)."""
        if not 2 <= num_players <= 6:
            raise ValueError("Coup supports 2 to 6 players")
        if names is not None and len(names) != num_players:
            raise ValueError(f"expected {num_players} names, got {len(names)}")
        self._max_turns = max_turns
        self._num_players = num_players
        self._names = list(names or DEFAULT_NAMES[:num_players])
        self._initial_hands = initial_hands
        self._initial_coins = initial_coins or {}
        self._starting_player = starting_player
        self._phase: str | None = None

    # ================================================================ lifecycle

    def reset(self, *, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._seed = seed
        ids = [f"p{i}" for i in range(self._num_players)]
        deck = list(FULL_DECK)
        hands: dict[str, list[Card]] = {}
        if self._initial_hands:
            for pid, cards in self._initial_hands.items():
                hands[pid] = [Card(c) for c in cards]
                for card in hands[pid]:
                    deck.remove(card)
        self._rng.shuffle(deck)
        for pid in ids:
            if pid not in hands:
                hands[pid] = [deck.pop(), deck.pop()]

        start = self._starting_player or ids[self._rng.randrange(self._num_players)]
        self._players = [
            Player(id=pid, name=name, coins=2, hidden=hands[pid]) for pid, name in zip(ids, self._names, strict=True)
        ]
        if self._num_players == 2:
            self._p(start).coins = 1  # rulebook: the starting player receives only 1 coin
        for pid, amount in self._initial_coins.items():
            self._p(pid).coins = amount
        self._deck = deck
        self._history: list[str] = []
        self._events: list[str] = []
        self._interaction_id = 0
        self._turn_number = 0
        self._turn: Turn | None = None
        self._eligible: list[str] = []
        self._loss_queue: list[tuple[str, str]] = []  # (player_id, reason)
        self._next: str | None = None  # continuation once the loss queue is empty
        self._exchange_draw: list[Card] = []
        self._winner: str | None = None
        self._turn_limit_reached = False
        self._start_player = start
        self._emit(f"Game starts with {self._num_players} players. {self._p(start).name} goes first.")
        self._start_turn(start)

    @property
    def player_ids(self) -> list[str]:
        return [p.id for p in self._players]

    def player_name(self, player_id: str) -> str:
        return self._p(player_id).name

    def config(self) -> dict:
        return {
            "num_players": self._num_players,
            "names": self._names,
            "starting_player": self._start_player,
            "fixed_initial_hands": self._initial_hands is not None,
            "fixed_initial_coins": bool(self._initial_coins),
            "max_turns": self._max_turns,
        }

    # ===================================================== what is happening now

    def current_interaction(self) -> Interaction | None:
        if self._phase is None:
            return None
        return Interaction(
            interaction_id=self._interaction_id,
            phase=self._phase,
            mode=PHASE_MODES[self._phase],
            eligible_players=tuple(self._eligible),
            message_policy=MessagePolicy.OPTIONAL,
            description=self._describe_interaction(),
        )

    def legal_actions(self, *, player_id: str) -> list[Action]:
        if self._phase is None or player_id not in self._eligible:
            return []
        me = self._p(player_id)
        if self._phase == "action":
            return self._legal_turn_actions(me)
        if self._phase in ("challenge_action", "challenge_block"):
            return [{"type": "pass"}, {"type": "challenge"}]
        if self._phase == "block_action":
            rule = ACTIONS[self._turn.action]
            return [{"type": "pass"}] + [{"type": "block", "claim": c.value} for c in rule.blockers]
        if self._phase == "lose_influence":
            return [{"type": "reveal", "card": c.value} for c in dict.fromkeys(me.hidden)]
        if self._phase == "exchange":
            return self._legal_keeps(me)
        raise AssertionError(self._phase)

    def _legal_turn_actions(self, me: Player) -> list[Action]:
        others = [p.id for p in self._players if p.alive and p.id != me.id]
        coup = [{"type": "coup", "target": t} for t in others]
        if me.coins >= FORCED_COUP_COINS:
            return coup  # rulebook: 10 or more coins at the start of the turn forces a Coup
        actions: list[Action] = [{"type": "income"}, {"type": "foreign_aid"}, {"type": "tax"}, {"type": "exchange"}]
        actions += [{"type": "steal", "target": t} for t in others]
        if me.coins >= ACTIONS["assassinate"].cost:
            actions += [{"type": "assassinate", "target": t} for t in others]
        if me.coins >= COUP_COST:
            actions += coup
        return actions

    def _legal_keeps(self, me: Player) -> list[Action]:
        pool = me.hidden + self._exchange_draw
        options: list[list[str]] = []
        for combo in combinations(range(len(pool)), len(me.hidden)):
            cards = sorted(pool[i].value for i in combo)
            if cards not in options:
                options.append(cards)
        current = sorted(c.value for c in me.hidden)
        options.sort(key=lambda cards: cards != current)  # keeping the current hand is listed first
        return [{"type": "keep", "cards": cards} for cards in options]

    # ============================================================ information

    def observe(self, *, player_id: str) -> dict:
        me = self._p(player_id)
        observation = {
            "game": "coup",
            "you": me.id,
            "your_name": me.name,
            "your_cards": [c.value for c in me.hidden],
            "your_coins": me.coins,
            **self.public_state(),
            "history": list(self._history),
        }
        if self._phase == "exchange" and self._turn and self._turn.actor == player_id:
            observation["exchange_drawn"] = [c.value for c in self._exchange_draw]
        return observation

    def public_state(self) -> dict:
        turn = self._turn
        pending = None
        if turn is not None and turn.action is not None:
            rule = ACTIONS[turn.action]
            pending = {
                "actor": turn.actor,
                "action": turn.action,
                "target": turn.target,
                "claim": rule.claim.value if rule.claim else None,
                "blocker": turn.blocker,
                "block_claim": turn.block_claim.value if turn.block_claim else None,
            }
        return {
            "turn": self._turn_number,
            "current_player": turn.actor if turn else None,
            "phase": self._phase,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "coins": p.coins,
                    "alive": p.alive,
                    "hidden_card_count": len(p.hidden),
                    "revealed_cards": [c.value for c in p.revealed],
                }
                for p in self._players
            ],
            "deck_size": len(self._deck),
            "pending_action": pending,
        }

    def public_history(self) -> list[str]:
        return list(self._history)

    def full_state(self) -> dict:
        return {
            "players": [
                {
                    "id": p.id,
                    "coins": p.coins,
                    "hidden": [c.value for c in p.hidden],
                    "revealed": [c.value for c in p.revealed],
                }
                for p in self._players
            ],
            "deck": [c.value for c in self._deck],
            "phase": self._phase,
            "eligible": list(self._eligible),
            "turn": self._turn_number,
            "loss_queue": [list(item) for item in self._loss_queue],
            "exchange_draw": [c.value for c in self._exchange_draw],
            "winner": self._winner,
            "turn_limit_reached": self._turn_limit_reached,
        }

    def result(self) -> GameResult | None:
        if self._turn_limit_reached:
            return GameResult(
                winners=[],
                payoffs={p.id: 0.0 for p in self._players},
                termination_reason="turn_limit",
            )
        if self._winner is None:
            return None
        return GameResult(
            winners=[self._winner],
            payoffs={p.id: 1.0 if p.id == self._winner else 0.0 for p in self._players},
            termination_reason="last_player_with_influence",
        )

    # ============================================================= transition

    def step(self, *, player_id: str, output: AgentOutput) -> StepResult:
        if self._phase is None:
            return StepResult(accepted=False, error="the game is over")
        if player_id not in self._eligible:
            return StepResult(accepted=False, error=f"{player_id} may not act in phase {self._phase!r}")
        action = self._normalise(output.action)
        legal = self.legal_actions(player_id=player_id)
        if action is None:
            return StepResult(accepted=False, error="no action given")
        if action not in legal:
            return StepResult(accepted=False, error=f"illegal action {action}; legal actions are {legal}")

        self._events = []
        if output.message and output.message.strip():
            self._emit(f'{self._p(player_id).name} says: "{output.message.strip()}"')
        handler = {
            "action": self._on_action,
            "challenge_action": self._on_challenge_action,
            "block_action": self._on_block_action,
            "challenge_block": self._on_challenge_block,
            "lose_influence": self._on_lose_influence,
            "exchange": self._on_exchange,
        }[self._phase]
        handler(player_id, action)
        return StepResult(accepted=True, public_events=list(self._events))

    @staticmethod
    def _normalise(action: Action | None) -> Action | None:
        if not isinstance(action, dict) or "type" not in action:
            return None
        if action.get("type") == "keep" and isinstance(action.get("cards"), list):
            return {"type": "keep", "cards": sorted(str(c) for c in action["cards"])}
        return dict(action)

    # ------------------------------------------------------------- the turn

    def _start_turn(self, actor: str) -> None:
        self._turn_number += 1
        self._turn = Turn(actor=actor)
        me = self._p(actor)
        self._emit(f"Turn {self._turn_number}: {me.name} ({_coins(me.coins)})")
        self._open("action", [actor])

    def _on_action(self, actor: str, action: Action) -> None:
        rule = ACTIONS[action["type"]]
        turn = self._turn
        turn.action, turn.target = rule.name, action.get("target")
        me = self._p(actor)
        if rule.cost:
            me.coins -= rule.cost
            turn.paid = rule.cost
        self._emit(self._describe_declaration(me, rule.name, turn.target))
        if rule.claim is not None:
            self._open("challenge_action", self._others_after(actor))
        elif rule.blockers:
            self._open_block_window()
        else:
            self._resolve_action()

    def _on_challenge_action(self, player: str, action: Action) -> None:
        if action["type"] == "pass":
            self._pass(player)
            if not self._eligible:
                self._action_claim_survives()
            return
        turn = self._turn
        claim = ACTIONS[turn.action].claim
        if self._resolve_challenge(challenger=player, claimant=turn.actor, card=claim):
            self._lose(player, reason="lost a challenge")
            self._next = "action_claim_survives"
        else:
            self._lose(turn.actor, reason="caught bluffing")
            if turn.paid:
                self._p(turn.actor).coins += turn.paid  # rulebook: a successfully challenged action refunds its cost
                self._emit(f"The action fails and {self._p(turn.actor).name} gets the {_coins(turn.paid)} back.")
            else:
                self._emit("The action fails.")
            self._next = "end_turn"
        self._proceed()

    def _action_claim_survives(self) -> None:
        turn = self._turn
        rule = ACTIONS[turn.action]
        if rule.targeted and not self._p(turn.target).alive:
            self._emit(f"{self._p(turn.target).name} is already out, so nothing more happens.")
            self._end_turn()
        elif rule.blockers:
            self._open_block_window()
        else:
            self._resolve_action()

    def _open_block_window(self) -> None:
        turn = self._turn
        rule = ACTIONS[turn.action]
        eligible = self._others_after(turn.actor) if rule.block_by_anyone else [turn.target]
        self._open("block_action", eligible)

    def _on_block_action(self, player: str, action: Action) -> None:
        if action["type"] == "pass":
            self._pass(player, text="does not block")
            if not self._eligible:
                self._resolve_action()
            return
        turn = self._turn
        turn.blocker, turn.block_claim = player, Card(action["claim"])
        self._emit(f"{self._p(player).name} claims {turn.block_claim.label} to block.")
        self._open("challenge_block", self._others_after(player))

    def _on_challenge_block(self, player: str, action: Action) -> None:
        if action["type"] == "pass":
            self._pass(player)
            if not self._eligible:
                self._block_stands()
            return
        turn = self._turn
        if self._resolve_challenge(challenger=player, claimant=turn.blocker, card=turn.block_claim):
            self._lose(player, reason="lost a challenge")
            self._next = "block_stands"
        else:
            self._lose(turn.blocker, reason="caught bluffing")
            self._emit("The block fails.")
            self._next = "resolve_action"
        self._proceed()

    def _block_stands(self) -> None:
        turn = self._turn
        spent = f" The {_coins(turn.paid)} stay spent." if turn.paid else ""
        self._emit(f"The block stands. {self._p(turn.actor).name}'s {turn.action} fails.{spent}")
        self._end_turn()

    def _resolve_action(self) -> None:
        turn = self._turn
        me = self._p(turn.actor)
        if turn.action == "income":
            me.coins += 1
        elif turn.action == "foreign_aid":
            me.coins += 2
        elif turn.action == "tax":
            me.coins += 3
        elif turn.action == "steal":
            target = self._p(turn.target)
            amount = min(2, target.coins)
            target.coins -= amount
            me.coins += amount
            self._emit(f"{me.name} steals {_coins(amount)} from {target.name}.")
        elif turn.action in ("coup", "assassinate"):
            if self._p(turn.target).alive:
                self._lose(turn.target, reason="hit by a coup" if turn.action == "coup" else "hit by an assassination")
            self._next = "end_turn"
            self._proceed()
            return
        elif turn.action == "exchange":
            self._exchange_draw = [self._deck.pop(), self._deck.pop()]
            self._emit(f"{me.name} draws 2 cards from the Court deck.")
            self._open("exchange", [me.id])
            return
        if turn.action in ("income", "foreign_aid", "tax"):
            self._emit(f"{me.name} now has {_coins(me.coins)}.")
        self._end_turn()

    def _on_exchange(self, player: str, action: Action) -> None:
        me = self._p(player)
        rest = me.hidden + self._exchange_draw
        keep = [Card(c) for c in action["cards"]]
        for card in keep:
            rest.remove(card)
        me.hidden = keep
        self._deck.extend(rest)
        self._rng.shuffle(self._deck)
        self._exchange_draw = []
        self._emit(f"{me.name} keeps {len(keep)} card(s) and returns 2 to the Court deck.")
        self._end_turn()

    # --------------------------------------------------- challenges and losses

    def _resolve_challenge(self, *, challenger: str, claimant: str, card: Card) -> bool:
        """Returns True if the claimant really had the card (the claim stands)."""
        c, ch = self._p(claimant), self._p(challenger)
        self._emit(f"{ch.name} challenges {c.name}'s claim to be {card.label}.")
        if card in c.hidden:
            # rulebook: reveal, shuffle it back into the Court deck, draw a replacement
            c.hidden.remove(card)
            self._deck.append(card)
            self._rng.shuffle(self._deck)
            c.hidden.append(self._deck.pop())
            self._emit(
                f"{c.name} reveals {card.label}, shuffles it back and draws a new card. "
                f"{ch.name} loses the challenge."
            )
            return True
        self._emit(f"{c.name} cannot show {card.label} and loses the challenge.")
        return False

    def _lose(self, player: str, *, reason: str) -> None:
        self._loss_queue.append((player, reason))

    def _proceed(self) -> None:
        """Resolve queued influence losses one at a time, then continue the turn."""
        while self._loss_queue:
            player, _ = self._loss_queue[0]
            if not self._p(player).alive:
                self._loss_queue.pop(0)
                continue
            self._open("lose_influence", [player])
            return
        if self._check_game_over():
            return
        step, self._next = self._next, None
        {
            "action_claim_survives": self._action_claim_survives,
            "block_stands": self._block_stands,
            "resolve_action": self._resolve_action,
            "end_turn": self._end_turn,
        }[step]()

    def _on_lose_influence(self, player: str, action: Action) -> None:
        me = self._p(player)
        _, reason = self._loss_queue.pop(0)
        card = Card(action["card"])
        me.hidden.remove(card)
        me.revealed.append(card)
        self._emit(f"{me.name} loses an influence ({reason}) and reveals {card.label}.")
        if not me.alive:
            me.coins = 0  # rulebook: an exiled player returns all coins to the Treasury
            self._emit(f"{me.name} has no influence left and is out of the game.")
        self._proceed()

    # ------------------------------------------------------------ end of turn

    def _end_turn(self) -> None:
        if self._check_game_over():
            return
        if self._turn_number >= self._max_turns:
            self._turn_limit_reached = True
            self._phase, self._eligible, self._turn = None, [], None
            self._emit(f"The turn limit ({self._max_turns}) is reached. The game ends without a winner.")
            return
        seats = self.player_ids
        i = seats.index(self._turn.actor)
        for step in range(1, len(seats) + 1):
            candidate = self._p(seats[(i + step) % len(seats)])
            if candidate.alive:
                self._start_turn(candidate.id)
                return

    def _check_game_over(self) -> bool:
        alive = [p for p in self._players if p.alive]
        if len(alive) != 1:
            return False
        self._winner = alive[0].id
        self._phase, self._eligible, self._turn = None, [], None
        self._emit(f"{alive[0].name} is the last player with influence and wins.")
        return True

    # ---------------------------------------------------------------- helpers

    def _p(self, player_id: str) -> Player:
        for p in self._players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)

    def _others_after(self, player_id: str) -> list[str]:
        """Alive players other than player_id, in seat order starting after them."""
        seats = self.player_ids
        i = seats.index(player_id)
        ordered = [seats[(i + k) % len(seats)] for k in range(1, len(seats))]
        return [pid for pid in ordered if self._p(pid).alive]

    def _open(self, phase: str, eligible: list[str]) -> None:
        self._phase = phase
        self._eligible = list(eligible)
        self._interaction_id += 1

    def _pass(self, player: str, *, text: str = "passes") -> None:
        self._eligible.remove(player)
        self._emit(f"{self._p(player).name} {text}.")

    def _emit(self, text: str) -> None:
        self._history.append(text)
        self._events.append(text)

    def _describe_declaration(self, me: Player, action: str, target: str | None) -> str:
        t = self._p(target).name if target else ""
        return {
            "income": f"{me.name} takes Income.",
            "foreign_aid": f"{me.name} asks for Foreign Aid.",
            "coup": f"{me.name} pays 7 coins and launches a Coup against {t}.",
            "tax": f"{me.name} claims the Duke and takes Tax.",
            "assassinate": f"{me.name} claims the Assassin, pays 3 coins and tries to assassinate {t}.",
            "steal": f"{me.name} claims the Captain and tries to steal from {t}.",
            "exchange": f"{me.name} claims the Ambassador and wants to exchange cards.",
        }[action]

    def _describe_interaction(self) -> str:
        turn = self._turn
        if self._phase == "action":
            return f"{self._p(turn.actor).name}'s turn: choose one action."
        if self._phase == "challenge_action":
            claim = ACTIONS[turn.action].claim
            return f"{self._p(turn.actor).name} claims {claim.label} ({turn.action}). Anyone may challenge."
        if self._phase == "block_action":
            options = " or ".join(c.label for c in ACTIONS[turn.action].blockers)
            return f"{self._p(turn.actor).name}'s {turn.action} may be blocked with {options}."
        if self._phase == "challenge_block":
            return f"{self._p(turn.blocker).name} claims {turn.block_claim.label} to block. Anyone may challenge."
        if self._phase == "lose_influence":
            player, reason = self._loss_queue[0]
            return f"{self._p(player).name} must reveal one card ({reason})."
        if self._phase == "exchange":
            return f"{self._p(turn.actor).name} must choose which cards to keep."
        return ""
