"""All games known to the framework. Adding a game = adding one entry to each dict."""

from selfplay_worlds.core.env import GameEnv
from selfplay_worlds.games.coup import RULES_TEXT as COUP_RULES
from selfplay_worlds.games.coup import CoupEnv, render_coup

ENVS: dict[str, type[GameEnv]] = {"coup": CoupEnv}
"""Game name -> environment class."""

RENDERERS = {"coup": render_coup}
"""Game name -> render(*, observation) -> str, used by Policy.render_observation."""

RULES: dict[str, str] = {"coup": COUP_RULES}
"""Game name -> plain-language rules, used in a Player's system prompt."""


def get_env_class(name: str) -> type[GameEnv]:
    try:
        return ENVS[name]
    except KeyError:
        raise KeyError(f"unknown game {name!r}; available: {sorted(ENVS)}") from None
