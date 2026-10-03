"""Coup: the first real game implemented on the framework."""

from selfplay_worlds.games.coup.actions import CoupAction, CoupActionType
from selfplay_worlds.games.coup.env import CoupEnv
from selfplay_worlds.games.coup.policies import CoupHeuristicPolicy
from selfplay_worlds.games.coup.prompts import RULES_TEXT, render_coup
from selfplay_worlds.games.coup.state import CoupPhase, CoupState

__all__ = [
    "CoupAction", "CoupActionType", "CoupEnv", "CoupHeuristicPolicy", "CoupPhase", "CoupState",
    "RULES_TEXT", "render_coup",
]
