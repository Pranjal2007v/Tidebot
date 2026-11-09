"""Checks on the static website in ``site/``."""

from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])


def _parse(name):
    parser = _Links()
    parser.feed((SITE / name).read_text(encoding="utf-8"))
    return parser


def _pages():
    return sorted(p.name for p in SITE.glob("*.html"))


def test_local_links_point_at_files_that_exist():
    for page in _pages():
        for link in _parse(page).links:
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = link.split("#")[0].split("?")[0]
            assert (SITE / target).is_file(), f"{page} links to missing {link}"


def test_landing_page_has_install_button_and_example_thread():
    page = _parse("index.html")
    assert "install" in page.ids and "example" in page.ids
    assert any(link.startswith("https://github.com/apps/") for link in page.links)
    text = (SITE / "index.html").read_text(encoding="utf-8")
    assert ":tide /" in text


def test_every_page_has_a_title_and_viewport():
    for page in _pages():
        text = (SITE / page).read_text(encoding="utf-8")
        assert "<title>" in text and 'name="viewport"' in text, page


def test_command_reference_is_up_to_date():
    from tidebot.sitegen import OUTPUT, render
    assert OUTPUT.read_text(encoding="utf-8") == render(), \
        "site/commands.html is stale; run python -m tidebot.sitegen"


def test_command_reference_lists_every_command_with_an_anchor():
    from tidebot.commands import ALL_COMMANDS
    page = _parse("commands.html")
    assert ALL_COMMANDS <= page.ids
    assert {"group-ai", "group-workflow", "group-community"} <= page.ids


def test_inline_escapes_html_and_formats_code():
    from tidebot.sitegen import inline
    assert inline("use `<b>` & **bold**") == "use <code>&lt;b&gt;</code> &amp; <strong>bold</strong>"


def test_command_reference_has_search_and_tier_filter():
    page = _parse("commands.html")
    assert {"search", "tier", "no-results"} <= page.ids
    assert "search.js" in page.links


def test_tier_levels_match_who_can_run_each_command():
    import re
    text = (SITE / "commands.html").read_text(encoding="utf-8")
    levels = dict(re.findall(r'id="([\w-]+)" data-level="(\d)"', text))
    assert levels["ask"] == "0" and levels["help"] == "0"
    assert levels["lgtm"] == "1" and levels["assign"] == "1"
    assert levels["merge"] == "2" and levels["label"] == "2"


def test_config_builder_is_up_to_date():
    from tidebot.sitegen import CONFIG_OUTPUT, render_config
    assert CONFIG_OUTPUT.read_text(encoding="utf-8") == render_config(), \
        "site/config.html is stale; run python -m tidebot.sitegen"


def test_config_builder_has_a_switch_per_option_at_its_default():
    import re
    from tidebot.config import options
    text = (SITE / "config.html").read_text(encoding="utf-8")
    page = _parse("config.html")
    assert {"options", "yaml", "copy"} <= page.ids
    for option in options():
        tag = re.search(rf'<input type="checkbox" id="{option.name}"[^>]*>', text).group(0)
        assert ("checked" in tag) is option.default, option.name


def test_config_builder_shows_yaml_that_parses_to_the_defaults():
    import html
    import re
    from tidebot.config import TideConfig, parse_config
    text = (SITE / "config.html").read_text(encoding="utf-8")
    yaml_text = html.unescape(re.search(r'<code id="yaml">(.*?)</code>', text, re.S).group(1))
    assert parse_config(yaml_text) == TideConfig()


def test_every_page_links_to_the_config_builder():
    for page in _pages():
        assert "config.html" in _parse(page).links, page
