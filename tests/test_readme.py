"""The README's command lists match the commands the bot knows."""

import re
from pathlib import Path

from tidebot.catalog import GROUPS

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def readme_section(title, level="##"):
    match = re.search(rf"^{level} {re.escape(title)}.*?\n(.*?)(?=^#{{2,{len(level)}}} )",
                      README, re.M | re.S)
    assert match, title
    return match.group(1)


def readme_group(group):
    heading = {"AI": "AI commands", "Workflow": "Workflow", "Community": "Community"}[group]
    return set(re.findall(r"`/([a-z-]+)", readme_section(heading, "###")))


def test_each_readme_group_lists_exactly_the_bots_commands():
    for group, names in GROUPS:
        assert readme_group(group) == set(names), group


def test_ai_group_count_in_the_heading_is_right():
    match = re.search(r"^### AI commands \((\d+)\)", README, re.M)
    ai = dict(GROUPS)["AI"]
    assert match and int(match.group(1)) == len(ai)
