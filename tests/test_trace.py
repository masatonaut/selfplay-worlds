"""The human-readable trace only prints what is public."""

from helpers import new_game

from selfplay_worlds.core import ConversationGame
from selfplay_worlds.episodes.trace import TracePrinter
from selfplay_worlds.policies import ReplayPolicy

HANDS = {"p0": ["captain", "assassin"], "p1": ["duke", "contessa"], "p2": ["ambassador", "duke"]}


def _trace(env, players):
    lines = []
    names = {pid: env.player_name(pid) for pid in env.player_ids}
    ConversationGame(env=env, players=players, on_entry=TracePrinter(names=names, write=lines.append)).run()
    return lines


def test_trace_shows_talk_the_response_window_and_the_outcome():
    players = {
        "p0": ReplayPolicy(game_name="coup", answers=[{"type": "tax"}], messages=["Duke, obviously."]),
        "p1": ReplayPolicy(game_name="coup", answers=[{"type": "challenge"}]),
        "p2": ReplayPolicy(game_name="coup"),
    }
    lines = _trace(new_game(HANDS), players)
    assert lines[:7] == [
        "    Game starts with 3 players. Alice goes first.",
        "\nTurn 1: Alice (2 coins)",
        '    Alice says: "Duke, obviously."',
        "    Alice claims the Duke and takes Tax.",
        "  [challenge_action] response window: Bob, Carol may respond",
        "    Bob challenges Alice's claim to be the Duke.",
        "    Alice cannot show the Duke and loses the challenge.",
    ]


def test_trace_reports_rejected_answers():
    players = {
        "p0": ReplayPolicy(game_name="coup", answers=[{"type": "fly"}]),
        "p1": ReplayPolicy(game_name="coup"),
        "p2": ReplayPolicy(game_name="coup"),
    }
    lines = _trace(new_game(HANDS), players)
    assert any(line.startswith("    ! Alice: invalid answer rejected (could not read the answer") for line in lines)


def test_trace_never_prints_private_thinking_or_opening_hands():
    lines = []
    printer = TracePrinter(write=lines.append)
    printer({"kind": "thinking", "visibility": "private", "player_id": "p0", "content": "I hold two Dukes."})
    env = new_game({"p0": ["duke", "duke"], "p1": ["duke", "captain"], "p2": ["contessa", "contessa"]})
    for text in env.get_state()["history"]:
        printer({"kind": "event", "visibility": "public", "player_id": None, "content": text})
    assert not any("duke" in line.lower() or "contessa" in line.lower() for line in lines)
