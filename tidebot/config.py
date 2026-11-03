"""Load a repo's ``.tide.yml`` settings.

See the README's Configuration section for what each option does. Unknown
keys are ignored and values of the wrong type fall back to the default, so a
typo in one repo's config never stops the bot from answering there.

Besides the on/off switches, ``reviewers`` maps code areas to the people
who review them, in CODEOWNERS pattern syntax::

    reviewers:
      docs/: [alice]
      "*.py": [bob, "@org/backend"]
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Mapping, Optional, Tuple

import yaml

from .owners import Rule

CONFIG_PATH = ".tide.yml"


@dataclass(frozen=True)
class TideConfig:
    auto_label: bool = True
    size_labels: bool = True
    star_gate: bool = False
    triage_label: bool = True
    pr_lint: bool = True
    reviewers: Tuple[Rule, ...] = ()

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "TideConfig":
        if not isinstance(data, Mapping):
            return cls()
        values: dict = {}
        for field in fields(cls):
            value = data.get(field.name)
            if field.type == "bool" and isinstance(value, bool):
                values[field.name] = value
        values["reviewers"] = _reviewer_rules(data.get("reviewers"))
        return cls(**values)


def _reviewer_rules(value: Any) -> Tuple[Rule, ...]:
    """Read the ``reviewers`` map, skipping entries that aren't pattern: [logins]."""
    if not isinstance(value, Mapping):
        return ()
    rules = []
    for pattern, people in value.items():
        if isinstance(people, str):
            people = [people]
        if not isinstance(pattern, str) or not isinstance(people, list):
            continue
        owners = tuple("@" + p.lstrip("@") for p in people if isinstance(p, str) and p.strip("@"))
        rules.append((pattern, owners))
    return tuple(rules)


def parse_config(text: Optional[str]) -> TideConfig:
    """Parse the contents of a ``.tide.yml`` file; bad YAML gives the defaults."""
    if not text:
        return TideConfig()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return TideConfig()
    return TideConfig.from_mapping(data)
