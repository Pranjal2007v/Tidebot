"""Load a repo's ``.tide.yml`` settings.

See the README's Configuration section for what each option does. Unknown
keys are ignored and values of the wrong type fall back to the default, so a
typo in one repo's config never stops the bot from answering there.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Mapping, Optional

import yaml

CONFIG_PATH = ".tide.yml"


@dataclass(frozen=True)
class TideConfig:
    auto_label: bool = True
    size_labels: bool = True
    star_gate: bool = False
    triage_label: bool = True
    pr_lint: bool = True

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "TideConfig":
        if not isinstance(data, Mapping):
            return cls()
        values = {}
        for field in fields(cls):
            value = data.get(field.name)
            if isinstance(value, bool):
                values[field.name] = value
        return cls(**values)


def parse_config(text: Optional[str]) -> TideConfig:
    """Parse the contents of a ``.tide.yml`` file; bad YAML gives the defaults."""
    if not text:
        return TideConfig()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return TideConfig()
    return TideConfig.from_mapping(data)
