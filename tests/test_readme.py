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


def test_rate_limits_match_the_readme():
    from tidebot import ratelimit
    match = re.search(r"(\d+) commands per hour per user and (\d+) per repo", README)
    assert match
    assert (int(match.group(1)), int(match.group(2))) == (ratelimit.PER_USER, ratelimit.PER_REPO)
    assert ratelimit.WINDOW_SECONDS == 3600


def test_review_numbers_match_the_readme():
    from tidebot import review
    steps = readme_section("How code review works")
    assert "four at a time" in steps and review.WORKERS == 4
    assert f"up to {review.MAX_FINDINGS} inline" in steps


def test_size_labels_span_the_readme_range():
    from tidebot.size import LABELS
    assert "`size/XS` to `size/XL`" in README
    assert set(LABELS) == {f"size/{s}" for s in ("XS", "S", "M", "L", "XL")}


def test_permission_table_matches_the_bot():
    from tidebot.commands import Command
    from tidebot.permissions import Tier, required_tier
    rows = {tier: set(re.findall(r"`/([a-z-]+)`", cells))
            for tier, cells in re.findall(r"^\| (Collaborator|Maintainer) \|[^|]*\|(.*)\|$",
                                          readme_section("Permissions"), re.M)}
    expected = {"Collaborator": Tier.COLLABORATOR, "Maintainer": Tier.MAINTAINER}
    for tier, names in rows.items():
        assert names, tier
        for name in names:
            assert required_tier(Command(name, ""), "someone") == expected[tier], name
    assert required_tier(Command("assign", ""), "someone") == Tier.COLLABORATOR
    assert required_tier(Command("assign", "@other"), "someone") == Tier.MAINTAINER
