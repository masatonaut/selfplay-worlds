"""The human-readable trace only prints what the environment made public."""

from helpers import new_game

from selfplay_worlds.agents.scripted import ScriptedAgent
from selfplay_worlds.core.runner import Runner
from selfplay_worlds.core.types import AgentOutput
from selfplay_worlds.episodes.trace import TracePrinter
from selfplay_worlds.games import get_game


def _trace(agents, **env_kwargs):
    lines = []
    env = get_game("coup").make_env(**env_kwargs)
    Runner(on_event=TracePrinter(write=lines.append)).run(env=env, agents=agents, seed=0)
    return lines


def test_trace_shows_the_response_window_and_the_outcome():
    hands = {"p0": ["captain", "assassin"], "p1": ["duke", "contessa"], "p2": ["ambassador", "duke"]}
    agents = {
        "p0": ScriptedAgent(script=[AgentOutput(action={"type": "tax"}, message="Duke, obviously.")]),
        "p1": ScriptedAgent(script=[AgentOutput(action={"type": "challenge"})]),
        "p2": ScriptedAgent(),
    }
    lines = _trace(agents, num_players=3, initial_hands=hands, starting_player="p0")
    assert lines[0] == "    Game starts with 3 players. Alice goes first."
    assert lines[1] == "\nTurn 1: Alice (2 coins)"
    assert lines[2] == '    Alice says: "Duke, obviously."'
    assert lines[3] == "    Alice claims the Duke and takes Tax."
    assert lines[4] == "  [challenge_action] response window: Bob, Carol may respond"
    assert lines[5] == "    Bob challenges Alice's claim to be the Duke."
    assert lines[6] == "    Alice cannot show the Duke and loses the challenge."


def test_trace_reports_rejected_outputs():
    agents = {
        "p0": ScriptedAgent(script=[AgentOutput(action={"type": "fly"})]),
        "p1": ScriptedAgent(),
        "p2": ScriptedAgent(),
    }
    lines = _trace(agents, num_players=3, starting_player="p0")
    assert any(line.startswith("    ! Alice: invalid output rejected (illegal action") for line in lines)


def test_trace_never_prints_hidden_cards_of_the_opening_hands():
    env = new_game({"p0": ["duke", "duke"], "p1": ["duke", "captain"], "p2": ["contessa", "contessa"]})
    printer_lines = []
    TracePrinter(write=printer_lines.append)({"kind": "reset", "public_events": env.public_history()})
    assert not any("duke" in line.lower() or "contessa" in line.lower() for line in printer_lines)
