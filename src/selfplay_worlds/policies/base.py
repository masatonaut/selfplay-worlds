"""A Policy turns what one seat may see into an answer (and, optionally, talk)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from selfplay_worlds.core.persist import load_pickle, save_pickle


class Policy(ABC):
    def __init__(self, *, game_name: str) -> None:
        if not game_name:
            raise ValueError("a policy needs the name of the game it plays")
        self.game_name = game_name
        self.last_thinking: str | None = None
        """Private reasoning from the latest call, if any. ConversationGame records it and clears it."""

    def render_observation(self, *, observation: dict[str, Any]) -> str:
        """The game's renderer if one is registered for ``game_name``, otherwise pretty JSON."""
        from selfplay_worlds.games import RENDERERS  # imported late: games import policies

        renderer = RENDERERS.get(self.game_name)
        if renderer is None:
            return json.dumps(observation, indent=2, sort_keys=True, default=str)
        return renderer(observation=observation)

    @abstractmethod
    def get_action(self, *, observation: dict[str, Any], conversation: list[dict[str, Any]]) -> dict[str, Any]:
        """Return an answer, for example ``{"option": 3}``.

        If ``observation`` has a ``"feedback"`` key, the previous answer was
        rejected and the value says why.
        """

    def get_message(self, *, observation: dict[str, Any], conversation: list[dict[str, Any]]) -> str | None:
        """What to say to the table during talk. Default: say nothing."""
        return None

    def describe(self) -> dict[str, Any]:
        """How this policy is recorded in a saved game."""
        return {"class": type(self).__name__, "game_name": self.game_name}

    def save(self, *, path: str | Path) -> Path:
        return save_pickle(path=path, value=self)

    def load(self, *, path: str | Path) -> None:
        saved = load_pickle(path=path)
        if type(saved) is not type(self):
            raise TypeError(f"{path} holds a {type(saved).__name__}, not a {type(self).__name__}")
        if saved.game_name != self.game_name:
            raise ValueError(f"{path} was saved for game {saved.game_name!r}, not {self.game_name!r}")
        self.__dict__.clear()
        self.__dict__.update(saved.__dict__)
