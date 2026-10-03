"""Atomic file writes for pickles and JSON. A crash never leaves a half-written file."""

from __future__ import annotations

import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any


def write_atomic(*, path: str | Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return path


def save_pickle(*, path: str | Path, value: Any) -> Path:
    return write_atomic(path=path, data=pickle.dumps(value))


def load_pickle(*, path: str | Path) -> Any:
    """Only ever load pickles this code wrote: unpickling runs code."""
    with Path(path).open("rb") as handle:
        return pickle.load(handle)


def save_json(*, path: str | Path, value: Any) -> Path:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    return write_atomic(path=path, data=text.encode("utf-8"))


def load_json(*, path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
