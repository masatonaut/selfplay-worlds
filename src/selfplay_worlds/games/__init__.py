"""All games known to the framework. Adding a game = adding one entry here."""

from selfplay_worlds.core.env import GameSpec
from selfplay_worlds.games.coup import SPEC as COUP

GAMES: dict[str, GameSpec] = {COUP.name: COUP}


def get_game(name: str) -> GameSpec:
    try:
        return GAMES[name]
    except KeyError:
        raise KeyError(f"unknown game {name!r}; available: {sorted(GAMES)}") from None
