"""The setup guide matches what the bot actually listens to and serves."""

import re
from pathlib import Path

from tidebot.app import _EVENT_HANDLERS, create_app
from tidebot.state import StateStore

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs" / "setup.md").read_text(encoding="utf-8")


def section(title):
    match = re.search(rf"^#+ {re.escape(title)}\n(.*?)(?=^#)", GUIDE, re.M | re.S)
    assert match, title
    return match.group(1)


def test_guide_subscribes_to_every_event_the_bot_handles():
    listed = {name.lower().replace(" ", "_")
              for name in re.findall(r"^- \*\*(.+?)\*\*$", section("Subscribe to events"), re.M)}
    handled = {event for event, _ in _EVENT_HANDLERS} | {"issue_comment"}
    assert listed == handled


def test_guide_urls_are_routes_on_the_bot():
    paths = {route.path for route in create_app("s", StateStore(None)).routes}
    for path in re.findall(r"https://bot\.example\.com(/[a-z/]+)", GUIDE):
        assert path in paths, path


def test_guide_names_only_settings_from_the_env_example():
    listed = set(re.findall(r"^(TIDEBOT_[A-Z_]+)=", (ROOT / ".env.example").read_text(), re.M))
    named = set(re.findall(r"TIDEBOT_[A-Z_]+", GUIDE))
    assert named and named <= listed


def test_guide_links_resolve():
    for target in re.findall(r"\]\((\.\./[^)#]+)", GUIDE):
        assert (ROOT / "docs" / target).resolve().exists(), target
