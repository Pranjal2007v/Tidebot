"""Settings that differ per installation of the GitHub App.

One hosted server runs the bot for everyone who installs the App, and not
every installation wants the same model. An installations file is a JSON
object keyed by installation id (the number in the App's installation URL):

    {
      "12345678": {
        "ai_url": "https://api.example.com/v1",
        "ai_model": "small-model",
        "ai_key": "optional"
      }
    }

An installation with no entry uses the server's own ``TIDEBOT_AI_*``
settings. The file holds API keys, so it is never committed. Every problem
becomes an ``InstallationsError`` that names the installation and the key
but never a value, so it is safe to print.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from .ai import AIClient

AI_KEYS = ("ai_url", "ai_model", "ai_key")
# Keys an entry must have; ``ai_key`` is optional, as it is for the server.
REQUIRED = ("ai_url", "ai_model")

Settings = Dict[int, Dict[str, str]]


class InstallationsError(Exception):
    """The installations file is wrong; the message holds no secret."""


def parse_installations(text: str) -> Settings:
    """Read the JSON text of an installations file into ``{id: settings}``."""
    try:
        data: Any = json.loads(text)
    except ValueError:
        raise InstallationsError("the installations file is not JSON") from None
    if not isinstance(data, dict):
        raise InstallationsError("the installations file must be an object keyed by "
                                 "installation id")
    settings: Settings = {}
    for key, entry in data.items():
        if not key.isascii() or not key.isdigit():
            raise InstallationsError("installation ids are numbers, but one key is not")
        where = f"installation {key}"
        if not isinstance(entry, dict):
            raise InstallationsError(f"{where} must be an object")
        unknown = sorted(set(entry) - set(AI_KEYS))
        if unknown:
            raise InstallationsError(f"{where} has unknown keys: " + ", ".join(unknown))
        clean = {}
        for name in AI_KEYS:
            value = entry.get(name, "")
            if not isinstance(value, str):
                raise InstallationsError(f"{where}: {name} must be text")
            if value.strip():
                clean[name] = value.strip()
        missing = [name for name in REQUIRED if name not in clean]
        if missing:
            raise InstallationsError(f"{where} is missing " + " and ".join(missing))
        settings[int(key)] = clean
    return settings


def load_installations(path: Union[str, Path]) -> Settings:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise InstallationsError(f"can't read the installations file at {path}") from None
    return parse_installations(text)


def ai_clients(settings: Settings) -> Dict[int, AIClient]:
    """One model client per installation that has its own AI settings."""
    return {installation: AIClient(entry["ai_url"], entry["ai_model"], entry.get("ai_key"))
            for installation, entry in settings.items()}
