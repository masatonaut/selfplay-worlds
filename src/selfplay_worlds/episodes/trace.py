"""Human-readable terminal trace.

Game-agnostic: it prints what the environment made public, plus the interaction
headers the Runner saw. It never looks at hidden state.
"""

from __future__ import annotations

from collections.abc import Callable


class TracePrinter:
    """Pass an instance as ``Runner(on_event=...)``."""

    def __init__(self, *, write: Callable[[str], None] = print) -> None:
        self._write = write
        self._names: dict[str, str] = {}
        self._last_interaction: int | None = None

    def __call__(self, event: dict) -> None:
        if event.get("kind") == "reset":
            self._names = dict(event.get("players", {}))
            self._last_interaction = None
            for line in event["public_events"]:
                self._line(line)
            return
        interaction = event["interaction"]
        if interaction["id"] != self._last_interaction:
            self._last_interaction = interaction["id"]
            if interaction["mode"] == "response_window":
                who = ", ".join(self._names.get(p, p) for p in interaction["eligible_players"])
                self._write(f"  [{interaction['phase']}] response window: {who} may respond")
        if not event["accepted"]:
            name = self._names.get(event["actor"], event["actor"])
            self._write(f"    ! {name}: invalid output rejected ({event['error']})")
        for line in event["public_events"]:
            self._line(line)

    def _line(self, line: str) -> None:
        if line.startswith("Turn "):
            self._write(f"\n{line}")
        else:
            self._write(f"    {line}")
