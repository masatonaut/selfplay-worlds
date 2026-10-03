"""Coup environment.

Rules: docs/coup-rules.md (verified against two transcriptions of the official
rulebook). One turn is modelled as explicit phases:

    action
      -> challenge_action   (if the action claims a character)
      -> block_action       (if the action can be blocked and survived)
      -> challenge_block    (if someone blocked)
      -> resolution         (automatic, no player input)

Two more ACTION phases interrupt a turn when needed:
    lose_influence  (a player must reveal a card)
    exchange        (the Ambassador chooses which cards to keep)

Every setting lives in ``game_config`` (see ``DEFAULT_CONFIG``).
"""

from __future__ import annotations

import random
from itertools import combinations
from typing import Any

from selfplay_worlds.core.env import DialogueMode, DialoguePhase, GameEnv, StepResult
from selfplay_worlds.games.coup.actions import CoupAction, CoupActionType
from selfplay_worlds.games.coup.cards import (
    ACTIONS,
    COUP_COST,
    FORCED_COUP_COINS,
    FULL_DECK,
    Card,
)
from selfplay_worlds.games.coup.state import (
    CoupContinuation,
    CoupPhase,
    CoupPlayerState,
    CoupState,
    CoupTurnState,
)

DEFAULT_NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
DEFAULT_MAX_TURNS = 100
"""Not a rule of Coup: a safety net so a game between agents that repeat the
same moves (for example two lone Captains stealing from each other and
blocking forever) still ends. See docs/coup-rules.md."""

DEFAULT_CONFIG: dict[str, Any] = {
    "num_players": 3,
    "names": None,  # None means the first num_players of DEFAULT_NAMES
    "initial_hands": None,
    "initial_coins": None,
    "starting_player": None,
    "max_turns": DEFAULT_MAX_TURNS,
    "seed": None,
}
"""``initial_hands`` / ``initial_coins`` / ``starting_player`` fix the opening position (tests and demos)."""

PHASES: dict[CoupPhase, tuple[DialogueMode, int]] = {
    # phase: (mode, talk rounds before acting)
    CoupPhase.ACTION: (DialogueMode.ACTION, 1),
    CoupPhase.CHALLENGE_ACTION: (DialogueMode.RESPONSE_WINDOW, 1),
    CoupPhase.BLOCK_ACTION: (DialogueMode.RESPONSE_WINDOW, 1),
    CoupPhase.CHALLENGE_BLOCK: (DialogueMode.RESPONSE_WINDOW, 1),
    CoupPhase.LOSE_INFLUENCE: (DialogueMode.ACTION, 0),
    CoupPhase.EXCHANGE: (DialogueMode.ACTION, 0),
}


def _coins(n: int) -> str:
    return "1 coin" if n == 1 else f"{n} coins"


class CoupEnv(GameEnv):
    action_class = CoupAction

    def __init__(self, *, game_config: dict[str, Any] | None = None) -> None:
        config = {**DEFAULT_CONFIG, **(game_config or {})}
        unknown = set(config) - set(DEFAULT_CONFIG)
        if unknown:
            raise ValueError(f"unknown Coup settings: {sorted(unknown)}")
        num_players = config["num_players"]
        if not 2 <= num_players <= 6:
            raise ValueError("Coup supports 2 to 6 players")
        if config["names"] is None:
            config["names"] = DEFAULT_NAMES[:num_players]
        elif len(config["names"]) != num_players:
            raise ValueError(f"expected {num_players} names, got {len(config['names'])}")
        config["names"] = list(config["names"])
        self._events: list[str] = []
        super().__init__(name="coup", game_config=config)

    # ================================================================ lifecycle

    def reset(self) -> None:
        super().reset()
        config = self.game_config
        num_players = config["num_players"]
        rng = random.Random(config["seed"])
        ids = [f"p{i}" for i in range(num_players)]
        deck = list(FULL_DECK)
        hands: dict[str, list[Card]] = {}
        for pid, cards in (config["initial_hands"] or {}).items():
            hands[pid] = [Card(c) for c in cards]
            for card in hands[pid]:
                deck.remove(card)
        rng.shuffle(deck)
        for pid in ids:
            if pid not in hands:
                hands[pid] = [deck.pop(), deck.pop()]

        start = config["starting_player"] or ids[rng.randrange(num_players)]
        players = [
            CoupPlayerState(id=pid, name=name, coins=2, hidden=hands[pid])
            for pid, name in zip(ids, config["names"], strict=True)
        ]
        self.state = CoupState(players=players, deck=deck, rng=rng, start_player=start)
        if num_players == 2:
            self._p(start).coins = 1  # rulebook: the starting player receives only 1 coin
        for pid, amount in (config["initial_coins"] or {}).items():
            self._p(pid).coins = amount
        self._events = []
        self._emit(f"Game starts with {num_players} players. {self._p(start).name} goes first.")
        self._start_turn(start)

    @property
    def player_ids(self) -> list[str]:
        return [p.id for p in self.state.players]

    def player_name(self, player_id: str) -> str:
        return self._p(player_id).name

    # ===================================================== what is happening now

    def get_dialogue_phase(self) -> DialoguePhase | None:
        s = self.state
        if s.phase is None:
            return None
        mode, talk_rounds = PHASES[s.phase]
        return DialoguePhase(
            phase_id=s.interaction_id,
            phase=s.phase.value,
            mode=mode,
            eligible=tuple(s.eligible_players),
            talk_rounds=talk_rounds,
            description=self._describe_interaction(),
        )

    def legal_actions(self, *, player_id: str) -> list[CoupAction]:
        """Legal actions in the current phase. By convention the first one is the most conservative."""
        s = self.state
        if s.phase is None or player_id not in s.eligible_players:
            return []
        me = self._p(player_id)
        if s.phase is CoupPhase.ACTION:
            return self._legal_turn_actions(me)
        if s.phase in (CoupPhase.CHALLENGE_ACTION, CoupPhase.CHALLENGE_BLOCK):
            return [CoupAction(CoupActionType.PASS), CoupAction(CoupActionType.CHALLENGE)]
        if s.phase is CoupPhase.BLOCK_ACTION:
            rule = ACTIONS[s.current_turn.action]
            return [CoupAction(CoupActionType.PASS)] + [
                CoupAction(CoupActionType.BLOCK, claim=card) for card in rule.blockers
            ]
        if s.phase is CoupPhase.LOSE_INFLUENCE:
            return [CoupAction(CoupActionType.REVEAL, card=card) for card in dict.fromkeys(me.hidden)]
        if s.phase is CoupPhase.EXCHANGE:
            return self._legal_keeps(me)
        raise AssertionError(s.phase)

    def _legal_turn_actions(self, me: CoupPlayerState) -> list[CoupAction]:
        others = [p.id for p in self.state.players if p.alive and p.id != me.id]
        coup = [CoupAction(CoupActionType.COUP, target=target) for target in others]
        if me.coins >= FORCED_COUP_COINS:
            return coup  # rulebook: 10 or more coins at the start of the turn forces a Coup
        actions = [
            CoupAction(CoupActionType.INCOME),
            CoupAction(CoupActionType.FOREIGN_AID),
            CoupAction(CoupActionType.TAX),
            CoupAction(CoupActionType.EXCHANGE),
        ]
        actions += [CoupAction(CoupActionType.STEAL, target=target) for target in others]
        if me.coins >= ACTIONS["assassinate"].cost:
            actions += [CoupAction(CoupActionType.ASSASSINATE, target=target) for target in others]
        if me.coins >= COUP_COST:
            actions += coup
        return actions

    def _legal_keeps(self, me: CoupPlayerState) -> list[CoupAction]:
        pool = me.hidden + self.state.exchange_draw
        options: list[list[str]] = []
        for combo in combinations(range(len(pool)), len(me.hidden)):
            cards = sorted(pool[i].value for i in combo)
            if cards not in options:
                options.append(cards)
        current = sorted(c.value for c in me.hidden)
        options.sort(key=lambda cards: cards != current)  # keeping the current hand is listed first
        return [CoupAction(CoupActionType.KEEP, cards=tuple(Card(card) for card in cards)) for cards in options]

    # ============================================================ information

    def get_observation(self, *, player_id: str) -> dict[str, Any]:
        s = self.state
        me = self._p(player_id)
        observation = {
            "game": "coup",
            "you": me.id,
            "your_name": me.name,
            "your_cards": [c.value for c in me.hidden],
            "your_coins": me.coins,
            **self._public_view(),
            "history": list(s.history),
            "decision": self._describe_interaction(),
            "decision_id": s.interaction_id,
            "options": [action.to_dict() for action in self.legal_actions(player_id=player_id)],
        }
        if s.phase is CoupPhase.EXCHANGE and s.current_turn and s.current_turn.actor == player_id:
            observation["exchange_drawn"] = [c.value for c in s.exchange_draw]
        return observation

    def get_state(self, *, view: str = "public") -> dict[str, Any]:
        """``view="public"``: what every player and spectator can see, with the history.
        ``view="full"``: the god view, including hidden cards. For tests and analysis only."""
        if view == "public":
            state = {**self._public_view(), "history": list(self.state.history)}
        elif view == "full":
            state = self._full_view()
        else:
            raise ValueError(f"unknown view {view!r}; use 'public' or 'full'")
        return {**state, **self._outcome()}

    def _public_view(self) -> dict[str, Any]:
        s = self.state
        turn = s.current_turn
        pending = None
        if turn is not None and turn.action is not None:
            rule = ACTIONS[turn.action]
            pending = {
                "actor": turn.actor,
                "action": turn.action.value,
                "target": turn.target,
                "claim": rule.claim.value if rule.claim else None,
                "blocker": turn.blocker,
                "block_claim": turn.block_claim.value if turn.block_claim else None,
            }
        return {
            "turn": s.turn_number,
            "current_player": turn.actor if turn else None,
            "phase": s.phase.value if s.phase else None,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "coins": p.coins,
                    "alive": p.alive,
                    "hidden_card_count": len(p.hidden),
                    "revealed_cards": [c.value for c in p.revealed],
                }
                for p in s.players
            ],
            "deck_size": len(s.deck),
            "pending_action": pending,
        }

    def _full_view(self) -> dict[str, Any]:
        s = self.state
        return {
            "players": [
                {
                    "id": p.id,
                    "coins": p.coins,
                    "hidden": [c.value for c in p.hidden],
                    "revealed": [c.value for c in p.revealed],
                }
                for p in s.players
            ],
            "deck": [c.value for c in s.deck],
            "phase": s.phase.value if s.phase else None,
            "eligible": list(s.eligible_players),
            "turn": s.turn_number,
            "loss_queue": [list(item) for item in s.loss_queue],
            "exchange_draw": [c.value for c in s.exchange_draw],
            "winner": s.winner,
            "turn_limit_reached": s.turn_limit_reached,
        }

    def _outcome(self) -> dict[str, Any]:
        s = self.state
        zeros = {p.id: 0.0 for p in s.players}
        if s.turn_limit_reached:
            return {"done": True, "rewards": zeros, "winners": [], "termination_reason": "turn_limit"}
        if s.winner is not None:
            rewards = {p.id: 1.0 if p.id == s.winner else 0.0 for p in s.players}
            return {"done": True, "rewards": rewards, "winners": [s.winner], "termination_reason": "last_player_with_influence"}
        return {"done": False, "rewards": zeros, "winners": [], "termination_reason": None}

    # ============================================================= transition

    def _step(self, *, player_id: str, action: CoupAction) -> StepResult:
        s = self.state
        if s.phase is None:
            return StepResult(accepted=False, error="the game is over")
        if player_id not in s.eligible_players:
            return StepResult(accepted=False, error=f"{player_id} may not act in phase {s.phase.value!r}")
        if not isinstance(action, CoupAction):
            return StepResult(accepted=False, error=f"not a Coup action: {action!r}")
        legal = self.legal_actions(player_id=player_id)
        if action not in legal:
            return StepResult(
                accepted=False,
                error=f"illegal action {action.to_dict()}; legal actions are {[item.to_dict() for item in legal]}",
            )

        self._events = []
        handler = {
            CoupPhase.ACTION: self._on_action,
            CoupPhase.CHALLENGE_ACTION: self._on_challenge_action,
            CoupPhase.BLOCK_ACTION: self._on_block_action,
            CoupPhase.CHALLENGE_BLOCK: self._on_challenge_block,
            CoupPhase.LOSE_INFLUENCE: self._on_lose_influence,
            CoupPhase.EXCHANGE: self._on_exchange,
        }[s.phase]
        handler(player_id, action)
        return StepResult(accepted=True, public_events=list(self._events))

    # ------------------------------------------------------------- the turn

    def _start_turn(self, actor: str) -> None:
        s = self.state
        s.turn_number += 1
        s.current_turn = CoupTurnState(actor=actor)
        me = self._p(actor)
        self._emit(f"Turn {s.turn_number}: {me.name} ({_coins(me.coins)})")
        self._open(CoupPhase.ACTION, [actor])

    def _on_action(self, actor: str, action: CoupAction) -> None:
        rule = ACTIONS[action.type]
        turn = self.state.current_turn
        turn.action, turn.target = CoupActionType(rule.name), action.target
        me = self._p(actor)
        if rule.cost:
            me.coins -= rule.cost
            turn.paid = rule.cost
        self._emit(self._describe_declaration(me, rule.name, turn.target))
        if rule.claim is not None:
            self._open(CoupPhase.CHALLENGE_ACTION, self._others_after(actor))
        elif rule.blockers:
            self._open_block_window()
        else:
            self._resolve_action()

    def _on_challenge_action(self, player: str, action: CoupAction) -> None:
        if action.type is CoupActionType.PASS:
            self._pass(player)
            if not self.state.eligible_players:
                self._action_claim_survives()
            return
        turn = self.state.current_turn
        claim = ACTIONS[turn.action].claim
        if self._resolve_challenge(challenger=player, claimant=turn.actor, card=claim):
            self._lose(player, reason="lost a challenge")
            self.state.continuation = CoupContinuation.ACTION_CLAIM_SURVIVES
        else:
            self._lose(turn.actor, reason="caught bluffing")
            if turn.paid:
                self._p(turn.actor).coins += turn.paid  # rulebook: a successfully challenged action refunds its cost
                self._emit(f"The action fails and {self._p(turn.actor).name} gets the {_coins(turn.paid)} back.")
            else:
                self._emit("The action fails.")
            self.state.continuation = CoupContinuation.END_TURN
        self._proceed()

    def _action_claim_survives(self) -> None:
        turn = self.state.current_turn
        rule = ACTIONS[turn.action]
        if rule.targeted and not self._p(turn.target).alive:
            self._emit(f"{self._p(turn.target).name} is already out, so nothing more happens.")
            self._end_turn()
        elif rule.blockers:
            self._open_block_window()
        else:
            self._resolve_action()

    def _open_block_window(self) -> None:
        turn = self.state.current_turn
        rule = ACTIONS[turn.action]
        eligible = self._others_after(turn.actor) if rule.block_by_anyone else [turn.target]
        self._open(CoupPhase.BLOCK_ACTION, eligible)

    def _on_block_action(self, player: str, action: CoupAction) -> None:
        if action.type is CoupActionType.PASS:
            self._pass(player, text="does not block")
            if not self.state.eligible_players:
                self._resolve_action()
            return
        turn = self.state.current_turn
        turn.blocker, turn.block_claim = player, action.claim
        self._emit(f"{self._p(player).name} claims {turn.block_claim.label} to block.")
        self._open(CoupPhase.CHALLENGE_BLOCK, self._others_after(player))

    def _on_challenge_block(self, player: str, action: CoupAction) -> None:
        if action.type is CoupActionType.PASS:
            self._pass(player)
            if not self.state.eligible_players:
                self._block_stands()
            return
        turn = self.state.current_turn
        if self._resolve_challenge(challenger=player, claimant=turn.blocker, card=turn.block_claim):
            self._lose(player, reason="lost a challenge")
            self.state.continuation = CoupContinuation.BLOCK_STANDS
        else:
            self._lose(turn.blocker, reason="caught bluffing")
            self._emit("The block fails.")
            self.state.continuation = CoupContinuation.RESOLVE_ACTION
        self._proceed()

    def _block_stands(self) -> None:
        turn = self.state.current_turn
        spent = f" The {_coins(turn.paid)} stay spent." if turn.paid else ""
        self._emit(f"The block stands. {self._p(turn.actor).name}'s {turn.action.value} fails.{spent}")
        self._end_turn()

    def _resolve_action(self) -> None:
        s = self.state
        turn = s.current_turn
        me = self._p(turn.actor)
        if turn.action is CoupActionType.INCOME:
            me.coins += 1
        elif turn.action is CoupActionType.FOREIGN_AID:
            me.coins += 2
        elif turn.action is CoupActionType.TAX:
            me.coins += 3
        elif turn.action is CoupActionType.STEAL:
            target = self._p(turn.target)
            amount = min(2, target.coins)
            target.coins -= amount
            me.coins += amount
            self._emit(f"{me.name} steals {_coins(amount)} from {target.name}.")
        elif turn.action in (CoupActionType.COUP, CoupActionType.ASSASSINATE):
            if self._p(turn.target).alive:
                reason = "hit by a coup" if turn.action is CoupActionType.COUP else "hit by an assassination"
                self._lose(turn.target, reason=reason)
            s.continuation = CoupContinuation.END_TURN
            self._proceed()
            return
        elif turn.action is CoupActionType.EXCHANGE:
            s.exchange_draw = [s.deck.pop(), s.deck.pop()]
            self._emit(f"{me.name} draws 2 cards from the Court deck.")
            self._open(CoupPhase.EXCHANGE, [me.id])
            return
        if turn.action in (CoupActionType.INCOME, CoupActionType.FOREIGN_AID, CoupActionType.TAX):
            self._emit(f"{me.name} now has {_coins(me.coins)}.")
        self._end_turn()

    def _on_exchange(self, player: str, action: CoupAction) -> None:
        s = self.state
        me = self._p(player)
        rest = me.hidden + s.exchange_draw
        keep = list(action.cards)
        for card in keep:
            rest.remove(card)
        me.hidden = keep
        s.deck.extend(rest)
        s.rng.shuffle(s.deck)
        s.exchange_draw = []
        self._emit(f"{me.name} keeps {len(keep)} card(s) and returns 2 to the Court deck.")
        self._end_turn()

    # --------------------------------------------------- challenges and losses

    def _resolve_challenge(self, *, challenger: str, claimant: str, card: Card) -> bool:
        """Returns True if the claimant really had the card (the claim stands)."""
        s = self.state
        c, ch = self._p(claimant), self._p(challenger)
        self._emit(f"{ch.name} challenges {c.name}'s claim to be {card.label}.")
        if card in c.hidden:
            # rulebook: reveal, shuffle it back into the Court deck, draw a replacement
            c.hidden.remove(card)
            s.deck.append(card)
            s.rng.shuffle(s.deck)
            c.hidden.append(s.deck.pop())
            self._emit(
                f"{c.name} reveals {card.label}, shuffles it back and draws a new card. "
                f"{ch.name} loses the challenge."
            )
            return True
        self._emit(f"{c.name} cannot show {card.label} and loses the challenge.")
        return False

    def _lose(self, player: str, *, reason: str) -> None:
        self.state.loss_queue.append((player, reason))

    def _proceed(self) -> None:
        """Resolve queued influence losses one at a time, then continue the turn."""
        s = self.state
        while s.loss_queue:
            player, _ = s.loss_queue[0]
            if not self._p(player).alive:
                s.loss_queue.pop(0)
                continue
            self._open(CoupPhase.LOSE_INFLUENCE, [player])
            return
        if self._check_game_over():
            return
        step, s.continuation = s.continuation, None
        {
            CoupContinuation.ACTION_CLAIM_SURVIVES: self._action_claim_survives,
            CoupContinuation.BLOCK_STANDS: self._block_stands,
            CoupContinuation.RESOLVE_ACTION: self._resolve_action,
            CoupContinuation.END_TURN: self._end_turn,
        }[step]()

    def _on_lose_influence(self, player: str, action: CoupAction) -> None:
        me = self._p(player)
        _, reason = self.state.loss_queue.pop(0)
        card = action.card
        me.hidden.remove(card)
        me.revealed.append(card)
        self._emit(f"{me.name} loses an influence ({reason}) and reveals {card.label}.")
        if not me.alive:
            me.coins = 0  # rulebook: an exiled player returns all coins to the Treasury
            self._emit(f"{me.name} has no influence left and is out of the game.")
        self._proceed()

    # ------------------------------------------------------------ end of turn

    def _end_turn(self) -> None:
        s = self.state
        if self._check_game_over():
            return
        if s.turn_number >= self.game_config["max_turns"]:
            s.turn_limit_reached = True
            s.phase, s.eligible_players, s.current_turn = None, [], None
            self._emit(f"The turn limit ({self.game_config['max_turns']}) is reached. The game ends without a winner.")
            return
        seats = self.player_ids
        i = seats.index(s.current_turn.actor)
        for step in range(1, len(seats) + 1):
            candidate = self._p(seats[(i + step) % len(seats)])
            if candidate.alive:
                self._start_turn(candidate.id)
                return

    def _check_game_over(self) -> bool:
        s = self.state
        alive = [p for p in s.players if p.alive]
        if len(alive) != 1:
            return False
        s.winner = alive[0].id
        s.phase, s.eligible_players, s.current_turn = None, [], None
        self._emit(f"{alive[0].name} is the last player with influence and wins.")
        return True

    # ---------------------------------------------------------------- helpers

    def _p(self, player_id: str) -> CoupPlayerState:
        for p in self.state.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)

    def _others_after(self, player_id: str) -> list[str]:
        """Alive players other than player_id, in seat order starting after them."""
        seats = self.player_ids
        i = seats.index(player_id)
        ordered = [seats[(i + k) % len(seats)] for k in range(1, len(seats))]
        return [pid for pid in ordered if self._p(pid).alive]

    def _open(self, phase: CoupPhase, eligible: list[str]) -> None:
        s = self.state
        s.phase = phase
        s.eligible_players = list(eligible)
        s.interaction_id += 1

    def _pass(self, player: str, *, text: str = "passes") -> None:
        self.state.eligible_players.remove(player)
        self._emit(f"{self._p(player).name} {text}.")

    def _emit(self, text: str) -> None:
        self.state.history.append(text)
        self._events.append(text)

    def _describe_declaration(self, me: CoupPlayerState, action: str, target: str | None) -> str:
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
        s = self.state
        turn = s.current_turn
        if s.phase is CoupPhase.ACTION:
            return f"{self._p(turn.actor).name}'s turn: choose one action."
        if s.phase is CoupPhase.CHALLENGE_ACTION:
            claim = ACTIONS[turn.action].claim
            return f"{self._p(turn.actor).name} claims {claim.label} ({turn.action.value}). Anyone may challenge."
        if s.phase is CoupPhase.BLOCK_ACTION:
            options = " or ".join(c.label for c in ACTIONS[turn.action].blockers)
            return f"{self._p(turn.actor).name}'s {turn.action.value} may be blocked with {options}."
        if s.phase is CoupPhase.CHALLENGE_BLOCK:
            return f"{self._p(turn.blocker).name} claims {turn.block_claim.label} to block. Anyone may challenge."
        if s.phase is CoupPhase.LOSE_INFLUENCE:
            player, reason = s.loss_queue[0]
            return f"{self._p(player).name} must reveal one card ({reason})."
        if s.phase is CoupPhase.EXCHANGE:
            return f"{self._p(turn.actor).name} must choose which cards to keep."
        return ""
