"""Coup rules, one scenario per test. Rules source: docs/coup-rules.md.

Seats: p0 Alice, p1 Bob, p2 Carol (Dave, Eve, Frank in bigger games).
"""

from helpers import (
    FULL_DECK_SORTED,
    act,
    all_cards,
    coins,
    eligible,
    hidden,
    new_game,
    phase,
    revealed,
)

from selfplay_worlds.core.interaction import InteractionMode
from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.games.coup import CoupEnv

# ------------------------------------------------------------ plain actions (SINGLE)


def test_income_resolves_without_any_response_window():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "income")
    assert coins(env, "p0") == 3
    assert phase(env) == "action" and eligible(env) == ["p1"]


def test_coup_costs_seven_and_cannot_be_challenged_or_blocked():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}, coins={"p0": 7})
    act(env, "p0", "coup", target="p1")
    assert coins(env, "p0") == 0
    assert phase(env) == "lose_influence" and eligible(env) == ["p1"]
    act(env, "p1", "reveal", card="assassin")
    assert revealed(env, "p1") == ["assassin"]
    assert phase(env) == "action" and eligible(env) == ["p1"]


# ------------------------------------------------ claims and challenges (RESPONSE_WINDOW)


def test_claim_opens_a_response_window_for_everyone_else_in_seat_order():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}, start="p1")
    act(env, "p1", "tax")
    interaction = env.current_interaction()
    assert interaction.phase == "challenge_action"
    assert interaction.mode is InteractionMode.RESPONSE_WINDOW
    assert interaction.eligible_players == ("p2", "p0")  # clockwise from the actor


def test_unchallenged_tax_gives_three_coins():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "tax")
    act(env, "p1", "pass")
    assert eligible(env) == ["p2"]  # a pass removes only that player from the window
    act(env, "p2", "pass")
    assert coins(env, "p0") == 5
    assert phase(env) == "action" and eligible(env) == ["p1"]


def test_first_challenge_closes_the_window():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "tax")
    act(env, "p1", "challenge")
    assert phase(env) == "lose_influence" and eligible(env) == ["p1"]
    assert env.legal_actions(player_id="p2") == []  # Carol is never asked


def test_failed_challenge_costs_the_challenger_and_the_claimant_draws_a_new_card():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "tax")
    act(env, "p1", "challenge")
    assert hidden(env, "p0")[0] == "captain" and len(hidden(env, "p0")) == 2  # Duke replaced
    act(env, "p1", "reveal", card="contessa")
    assert coins(env, "p0") == 5  # the action still happens
    assert revealed(env, "p1") == ["contessa"]
    assert all_cards(env) == FULL_DECK_SORTED


def test_successful_challenge_makes_the_action_fail():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "tax")  # bluff: Alice has no Duke
    act(env, "p1", "challenge")
    assert phase(env) == "lose_influence" and eligible(env) == ["p0"]
    act(env, "p0", "reveal", card="assassin")
    assert coins(env, "p0") == 2
    assert "The action fails." in env.public_history()
    assert phase(env) == "action" and eligible(env) == ["p1"]


def test_successfully_challenged_assassination_refunds_the_three_coins():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    assert coins(env, "p0") == 0  # paid up front
    act(env, "p1", "challenge")
    assert coins(env, "p0") == 3  # refunded
    act(env, "p0", "reveal", card="captain")
    assert len(hidden(env, "p1")) == 2
    assert "The action fails and Alice gets the 3 coins back." in env.public_history()


# ------------------------------------------------------------------- blocks


def test_foreign_aid_can_be_blocked_by_any_other_player():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "foreign_aid")
    assert phase(env) == "block_action" and eligible(env) == ["p1", "p2"]
    act(env, "p1", "pass")
    act(env, "p2", "block", claim="duke")
    assert phase(env) == "challenge_block" and eligible(env) == ["p0", "p1"]
    act(env, "p0", "pass")
    act(env, "p1", "pass")
    assert coins(env, "p0") == 2
    assert "The block stands. Alice's foreign_aid fails." in env.public_history()


def test_unblocked_foreign_aid_gives_two_coins():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "foreign_aid")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    assert coins(env, "p0") == 4


def test_only_the_target_may_block_a_steal():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "steal", target="p1")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    assert phase(env) == "block_action" and eligible(env) == ["p1"]
    act(env, "p1", "pass")
    assert (coins(env, "p0"), coins(env, "p1")) == (4, 0)


def test_steal_takes_only_one_coin_from_a_player_with_one_coin():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]}, coins={"p1": 1})
    act(env, "p0", "steal", target="p1")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    act(env, "p1", "pass")
    assert (coins(env, "p0"), coins(env, "p1")) == (3, 0)
    assert "Alice steals 1 coin from Bob." in env.public_history()


def test_blocked_assassination_keeps_the_three_coins_spent():
    env = new_game({"p0": ["assassin", "duke"], "p1": ["contessa", "captain"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    assert phase(env) == "block_action" and eligible(env) == ["p1"]
    act(env, "p1", "block", claim="contessa")
    act(env, "p2", "pass")
    act(env, "p0", "pass")
    assert coins(env, "p0") == 0  # a blocked action is not refunded
    assert len(hidden(env, "p1")) == 2
    assert "The block stands. Alice's assassinate fails. The 3 coins stay spent." in env.public_history()


# ---------------------------------------------------- nested challenge of a block


def test_challenging_a_true_block_costs_the_challenger_and_the_block_stands():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "foreign_aid")
    act(env, "p1", "pass")
    act(env, "p2", "block", claim="duke")
    act(env, "p0", "challenge")
    assert phase(env) == "lose_influence" and eligible(env) == ["p0"]
    act(env, "p0", "reveal", card="assassin")
    assert coins(env, "p0") == 2
    assert len(hidden(env, "p2")) == 2  # Carol showed the Duke and drew a new card
    assert phase(env) == "action" and eligible(env) == ["p1"]


def test_challenging_a_bluffed_block_lets_the_action_resolve():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["captain", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "foreign_aid")
    act(env, "p1", "block", claim="duke")  # bluff: Bob has no Duke
    act(env, "p2", "challenge")
    act(env, "p1", "reveal", card="contessa")
    assert coins(env, "p0") == 4
    assert "The block fails." in env.public_history()


def test_steal_blocked_with_a_bluffed_ambassador_is_challenged():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["duke", "contessa"], "p2": ["duke", "ambassador"]})
    act(env, "p0", "steal", target="p1")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    act(env, "p1", "block", claim="ambassador")
    assert eligible(env) == ["p2", "p0"]
    act(env, "p2", "pass")
    act(env, "p0", "challenge")
    act(env, "p1", "reveal", card="duke")
    assert (coins(env, "p0"), coins(env, "p1")) == (4, 0)


# ------------------------------------------------ double danger and elimination


def test_losing_a_challenge_then_being_assassinated_removes_two_influences():
    env = new_game({"p0": ["assassin", "duke"], "p1": ["captain", "contessa"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    act(env, "p1", "challenge")  # Alice really has the Assassin
    act(env, "p1", "reveal", card="captain")
    assert phase(env) == "block_action" and eligible(env) == ["p1"]  # Bob may still block
    act(env, "p1", "pass")
    assert phase(env) == "lose_influence" and eligible(env) == ["p1"]
    act(env, "p1", "reveal", card="contessa")
    assert hidden(env, "p1") == [] and coins(env, "p1") == 0
    assert "Bob has no influence left and is out of the game." in env.public_history()


def test_bluffed_contessa_that_is_challenged_loses_two_influences():
    env = new_game({"p0": ["assassin", "duke"], "p1": ["captain", "duke"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    act(env, "p1", "block", claim="contessa")  # bluff
    act(env, "p2", "pass")
    act(env, "p0", "challenge")
    act(env, "p1", "reveal", card="captain")  # for the failed bluff
    act(env, "p1", "reveal", card="duke")  # for the assassination
    assert hidden(env, "p1") == []
    assert phase(env) == "action" and eligible(env) == ["p2"]


def test_a_player_may_block_after_losing_a_challenge_against_the_same_action():
    """Interpretation documented in docs/coup-rules.md: phases are serialised."""
    env = new_game({"p0": ["assassin", "duke"], "p1": ["captain", "contessa"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    act(env, "p1", "challenge")
    act(env, "p1", "reveal", card="captain")
    act(env, "p1", "block", claim="contessa")
    act(env, "p2", "pass")
    act(env, "p0", "pass")
    assert hidden(env, "p1") == ["contessa"]


def test_eliminated_players_are_skipped_in_turns_and_response_windows():
    env = new_game({"p0": ["assassin", "duke"], "p1": ["captain"], "p2": ["ambassador", "duke"]}, coins={"p0": 7})
    act(env, "p0", "coup", target="p1")
    act(env, "p1", "reveal", card="captain")
    assert phase(env) == "action" and eligible(env) == ["p2"]  # Bob's seat is skipped
    act(env, "p2", "tax")
    assert eligible(env) == ["p0"]  # Bob cannot respond any more
    assert env.legal_actions(player_id="p1") == []


def test_target_eliminated_by_a_lost_challenge_ends_the_action():
    env = new_game({"p0": ["assassin", "duke"], "p1": ["captain"], "p2": ["ambassador", "duke"]}, coins={"p0": 3})
    act(env, "p0", "assassinate", target="p1")
    act(env, "p1", "challenge")
    act(env, "p1", "reveal", card="captain")
    assert "Bob is already out, so nothing more happens." in env.public_history()
    assert phase(env) == "action" and eligible(env) == ["p2"]


# ----------------------------------------------------------------- exchange


def test_exchange_draws_two_and_returns_two():
    env = new_game({"p0": ["ambassador", "captain"], "p1": ["contessa", "assassin"], "p2": ["duke", "duke"]})
    deck_size = len(env.full_state()["deck"])
    act(env, "p0", "exchange")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    assert phase(env) == "exchange" and eligible(env) == ["p0"]
    drawn = env.observe(player_id="p0")["exchange_drawn"]
    act(env, "p0", "keep", cards=sorted(["captain", drawn[0]]))
    assert sorted(hidden(env, "p0")) == sorted(["captain", drawn[0]])
    assert len(env.full_state()["deck"]) == deck_size
    assert all_cards(env) == FULL_DECK_SORTED


# ------------------------------------------------------- end of game and talk


def test_last_player_with_influence_wins():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa"]}, coins={"p0": 7})
    act(env, "p0", "coup", target="p1")
    act(env, "p1", "reveal", card="contessa")
    assert env.current_interaction() is None
    assert env.is_terminal()
    result = env.result()
    assert result.winners == ["p0"]
    assert result.payoffs == {"p0": 1.0, "p1": 0.0}
    assert result.termination_reason == "last_player_with_influence"
    assert env.public_history()[-1] == "Alice is the last player with influence and wins."


def test_nothing_is_accepted_after_the_game_ends():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa"]}, coins={"p0": 7})
    act(env, "p0", "coup", target="p1")
    act(env, "p1", "reveal", card="contessa")
    result = env.step(player_id="p0", output=AgentOutput(action={"type": "income"}))
    assert not result.accepted and result.error == "the game is over"
    assert env.legal_actions(player_id="p0") == []


def test_turn_limit_ends_the_game_without_a_winner():
    """Not a Coup rule: a safety net for agents that loop (docs/coup-rules.md)."""
    env = CoupEnv(num_players=3, starting_player="p0", max_turns=2)
    env.reset(seed=0)
    act(env, "p0", "income")
    act(env, "p1", "income")
    assert env.current_interaction() is None
    result = env.result()
    assert result.winners == [] and result.termination_reason == "turn_limit"
    assert result.payoffs == {"p0": 0.0, "p1": 0.0, "p2": 0.0}
    assert env.public_history()[-1] == "The turn limit (2) is reached. The game ends without a winner."


def test_result_is_none_while_the_game_is_running():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "assassin"]})
    assert env.result() is None


def test_messages_are_public_and_separate_from_the_action():
    env = new_game({"p0": ["captain", "assassin"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]})
    result = act(env, "p0", "tax", message="I have the Duke, trust me.")
    assert result.public_events[0] == 'Alice says: "I have the Duke, trust me."'
    assert result.public_events[1] == "Alice claims the Duke and takes Tax."
    assert env.public_state()["pending_action"]["claim"] == "duke"  # the action, not the words, is the claim
