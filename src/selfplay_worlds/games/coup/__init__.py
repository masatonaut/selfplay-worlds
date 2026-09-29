"""Coup: the first real game implemented on the framework."""

from selfplay_worlds.core.env import GameSpec
from selfplay_worlds.games.coup.actions import CoupAction, CoupActionType
from selfplay_worlds.games.coup.env import CoupEnv
from selfplay_worlds.games.coup.policies import heuristic_policy
from selfplay_worlds.games.coup.prompts import RULES_TEXT, render_observation
from selfplay_worlds.games.coup.state import CoupPhase, CoupState

SPEC = GameSpec(
    name="coup",
    make_env=CoupEnv,
    rules_text=RULES_TEXT,
    render_observation=render_observation,
    scripted_policy=heuristic_policy,
)

__all__ = ["CoupAction", "CoupActionType", "CoupEnv", "CoupPhase", "CoupState", "SPEC"]
