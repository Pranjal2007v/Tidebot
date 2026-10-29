"""Keep the bot's state in a single JSON file.

The README's Architecture section keeps all state in one JSON file so the
bot fits on a small VM with no database. Each module owns one top-level key.
Writes go to a temporary file first and are then renamed over the old one,
so a crash mid-write never leaves a half-written file behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

DEFAULT_PATH = "state.json"


class StateStore:
    def __init__(self, path: Optional[Union[str, Path]] = DEFAULT_PATH):
        # A path of None keeps state in memory only, which tests use.
        self.path = Path(path) if path is not None else None
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path is None or not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise
