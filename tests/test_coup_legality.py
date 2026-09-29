"""Legal actions, and rejection of invalid outputs."""

import pytest
from helpers import act, new_game

from selfplay_worlds.core.types import AgentOutput

HANDS = {"p0": ["duke", "captain"], "p1": ["contessa", "assassin"], "p2": ["ambassador", "duke"]}


def _types(actions):
    return [action.type.value for action in actions]


def _dicts(actions):
    return [action.to_dict() for action in actions]


def test_turn_actions_with_two_coins():
    env = new_game(HANDS)
    legal = env.legal_actions(player_id="p0")
    assert _dicts(legal) == [
        {"type": "income"},
        {"type": "foreign_aid"},
        {"type": "tax"},
        {"type": "exchange"},
        {"type": "steal", "target": "p1"},
        {"type": "steal", "target": "p2"},
    ]


def test_assassinate_needs_three_coins_and_coup_needs_seven():
    assert "assassinate" in _types(new_game(HANDS, coins={"p0": 3}).legal_actions(player_id="p0"))
    assert "coup" not in _types(new_game(HANDS, coins={"p0": 6}).legal_actions(player_id="p0"))
    assert "coup" in _types(new_game(HANDS, coins={"p0": 7}).legal_actions(player_id="p0"))


def test_ten_coins_force_a_coup():
    env = new_game(HANDS, coins={"p0": 10})
    assert _dicts(env.legal_actions(player_id="p0")) == [
        {"type": "coup", "target": "p1"},
        {"type": "coup", "target": "p2"},
    ]


def test_players_who_may_not_act_have_no_legal_actions():
    env = new_game(HANDS)
    assert env.legal_actions(player_id="p1") == []
    assert env.legal_actions(player_id="p2") == []


def test_challenge_windows_offer_pass_or_challenge():
    env = new_game(HANDS)
    act(env, "p0", "tax")
    assert _dicts(env.legal_actions(player_id="p1")) == [{"type": "pass"}, {"type": "challenge"}]


@pytest.mark.parametrize(
    "action, blocks",
    [
        ({"type": "foreign_aid"}, [{"type": "block", "claim": "duke"}]),
        ({"type": "steal", "target": "p1"}, [{"type": "block", "claim": "captain"}, {"type": "block", "claim": "ambassador"}]),
        ({"type": "assassinate", "target": "p1"}, [{"type": "block", "claim": "contessa"}]),
    ],
)
def test_block_options_follow_the_action_table(action, blocks):
    env = new_game(HANDS, coins={"p0": 3})
    assert env.step(player_id="p0", output=AgentOutput(action=action)).accepted
    while env.current_interaction().phase == "challenge_action":
        act(env, env.current_interaction().eligible_players[0], "pass")
    assert env.current_interaction().phase == "block_action"
    blocker = env.current_interaction().eligible_players[0]
    assert _dicts(env.legal_actions(player_id=blocker)) == [{"type": "pass"}] + blocks


def test_lose_influence_offers_each_distinct_hidden_card():
    env = new_game({"p0": ["duke", "captain"], "p1": ["contessa", "contessa"], "p2": ["ambassador", "duke"]})
    act(env, "p0", "tax")
    act(env, "p1", "challenge")
    assert env.current_interaction().phase == "lose_influence"
    assert _dicts(env.legal_actions(player_id="p1")) == [{"type": "reveal", "card": "contessa"}]


def test_exchange_lists_keeping_the_current_hand_first():
    env = new_game({"p0": ["ambassador", "captain"], "p1": ["contessa", "assassin"], "p2": ["duke", "duke"]})
    act(env, "p0", "exchange")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    legal = env.legal_actions(player_id="p0")
    assert legal[0].to_dict() == {"type": "keep", "cards": ["ambassador", "captain"]}
    assert all(len(action.cards) == 2 for action in legal)
    assert len(legal) == len({action.cards for action in legal})  # no duplicates


# ---------------------------------------------------------------- invalid outputs


@pytest.mark.parametrize(
    "player_id, output, error",
    [
        ("p1", AgentOutput(action={"type": "income"}), "may not act"),
        ("p0", AgentOutput(action={"type": "coup", "target": "p1"}), "illegal action"),
        ("p0", AgentOutput(action={"type": "steal", "target": "p0"}), "illegal action"),
        ("p0", AgentOutput(action={"type": "fly"}), "illegal action"),
        ("p0", AgentOutput(action=None, message="I am thinking."), "no action given"),
        ("p0", AgentOutput(action="tax"), "no action given"),
    ],
)
def test_invalid_outputs_are_rejected_and_change_nothing(player_id, output, error):
    env = new_game(HANDS)
    before = (env.full_state(), env.public_history(), env.current_interaction())
    result = env.step(player_id=player_id, output=output)
    assert not result.accepted
    assert error in result.error
    assert (env.full_state(), env.public_history(), env.current_interaction()) == before


def test_rejection_lists_the_legal_actions_as_feedback():
    env = new_game(HANDS)
    result = env.step(player_id="p0", output=AgentOutput(action={"type": "coup", "target": "p1"}))
    assert "legal actions are" in result.error
    assert "'income'" in result.error


def test_keep_order_does_not_matter():
    env = new_game({"p0": ["ambassador", "captain"], "p1": ["contessa", "assassin"], "p2": ["duke", "duke"]})
    act(env, "p0", "exchange")
    act(env, "p1", "pass")
    act(env, "p2", "pass")
    act(env, "p0", "keep", cards=["captain", "ambassador"])  # unsorted on purpose
    assert env.current_interaction().phase == "action"
