"""Human-readable terminal trace.

Game-agnostic: it prints conversation-record entries as they are appended. The
record holds only what happened at the table, never hidden state or private reasoning.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class TracePrinter:
    """Pass an instance as ``ConversationGame(on_entry=...)``."""

    def __init__(self, *, names: dict[str, str] | None = None, write: Callable[[str], None] = print) -> None:
        self._names = dict(names or {})
        self._write = write

    def __call__(self, entry: dict[str, Any]) -> None:
        kind = entry["kind"]
        if kind == "event":
            self._line(entry["content"])
        elif kind == "message":
            self._write(f'    {self._name(entry["player_id"])} says: "{entry["content"]}"')
        elif kind == "phase" and entry["mode"] == "response_window":
            who = ", ".join(self._name(pid) for pid in entry["eligible"])
            self._write(f"  [{entry['phase']}] response window: {who} may respond")
        elif kind == "action" and not entry["accepted"]:
            self._write(f"    ! {self._name(entry['player_id'])}: invalid answer rejected ({entry['error']})")

    def _name(self, player_id: str | None) -> str:
        return self._names.get(player_id, player_id or "?")

    def _line(self, line: str) -> None:
        if line.startswith("Turn "):
            self._write(f"\n{line}")
        else:
            self._write(f"    {line}")
