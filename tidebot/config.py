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

import json

from dataclasses import asdict, dataclass, fields
from typing import Any, List, Mapping, NamedTuple, Optional, Tuple

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
    duplicate_check: bool = True
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


class Option(NamedTuple):
    """One on/off switch in ``.tide.yml``, as the config builder shows it."""
    name: str
    default: bool
    help: str


_HELP = {
    "auto_label": "Label new issues by their content.",
    "size_labels": "Add a size/XS to size/XL label to every PR.",
    "star_gate": "Only people who starred the repo can run AI commands, stats and help.",
    "triage_label": "Add a triage label to new issues until a maintainer looks.",
    "pr_lint": "Check new PR titles and descriptions.",
    "duplicate_check": "Look for duplicates among open issues when an issue opens.",
}


def options() -> List[Option]:
    """Every on/off switch with its default, in the order of ``TideConfig``."""
    defaults = asdict(TideConfig())
    return [Option(f.name, defaults[f.name], _HELP[f.name])
            for f in fields(TideConfig) if f.type == "bool"]


def to_yaml(config: TideConfig) -> str:
    """Write ``config`` as ``.tide.yml`` text that ``parse_config`` reads back."""
    lines = [f"{o.name}: {'true' if getattr(config, o.name) else 'false'}" for o in options()]
    if config.reviewers:
        lines.append("reviewers:")
        for pattern, owners in config.reviewers:
            people = ", ".join(json.dumps(o) for o in owners)
            lines.append(f"  {json.dumps(pattern)}: [{people}]")
    return "\n".join(lines) + "\n"


def parse_config(text: Optional[str]) -> TideConfig:
    """Parse the contents of a ``.tide.yml`` file; bad YAML gives the defaults."""
    if not text:
        return TideConfig()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return TideConfig()
    return TideConfig.from_mapping(data)
