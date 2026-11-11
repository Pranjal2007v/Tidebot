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


def _node(script):
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    run = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    return run.stdout


def test_config_builder_loads_its_script_and_reviewers_box():
    page = _parse("config.html")
    assert "config.js" in page.links and "reviewers" in page.ids


def test_config_script_writes_the_same_yaml_as_the_bot():
    import json
    from tidebot.config import options, parse_config, to_yaml
    switches = [{"name": o.name, "on": o.name != "pr_lint"} for o in options()]
    reviewers = "docs/: alice, @@bob\n*.py: @org/backend\nno colon here\nsrc/:\n"
    script = (f"const c = require({json.dumps(str(SITE / 'config.js'))});"
              f"process.stdout.write(c.tideYaml({json.dumps(switches)}, {json.dumps(reviewers)}));")
    text = _node(script)
    cfg = parse_config(text)
    assert cfg.pr_lint is False and cfg.star_gate is True
    assert cfg.reviewers == (("docs/", ("@alice", "@bob")), ("*.py", ("@org/backend",)))
    assert text == to_yaml(cfg)


def test_every_page_links_to_the_dashboard():
    for page in _pages():
        assert "dashboard.html" in _parse(page).links, page


def test_dashboard_has_its_form_and_script():
    page = _parse("dashboard.html")
    assert "dashboard.js" in page.links
    assert {"lookup", "server", "repo", "repos", "token", "status", "numbers",
            "signin", "signout", "who"} <= page.ids


def test_dashboard_script_turns_a_stats_report_into_four_cards():
    import json
    from tidebot.metrics import Metrics
    from tidebot.state import StateStore
    store = StateStore(None)
    store.set("stats", {"o/r": {"review": 3, "ping": 1}})
    m = Metrics(store)
    for seconds in (1.0, 2.5, 95.0):
        m.record_wait("o/r", seconds)
    m.record_reply("o/r", "review")
    m.record_duplicates("o/r", 4)
    script = (f"const d = require({json.dumps(str(SITE / 'dashboard.js'))});"
              f"process.stdout.write(JSON.stringify({{cards: d.cards({json.dumps(m.report('o/r'))}),"
              "empty: d.cards({repo: 'o/r'}), url: d.statsUrl('https://bot.test/', 'o/r'),"
              "list: d.statsUrl('https://bot.test'),"
              "problems: [401, 404, 500, 403].map(d.problem),"
              "login: d.loginUrl('https://bot.test/', 'https://dash.test/dashboard.html?x=1'),"
              "me: d.authUrl('https://bot.test//', 'me'),"
              "bare: d.request(''), withToken: d.request('t0k')}));")
    out = json.loads(_node(script))
    assert [c["label"] for c in out["cards"]] == [
        "Commands run", "Median queue wait", "Reviews posted", "Duplicates caught"]
    assert [c["value"] for c in out["cards"]] == ["4", "2.5s", "1", "1"]
    assert out["cards"][0]["detail"] == "/review 3, /ping 1"
    assert out["cards"][1]["detail"] == "3 AI jobs, longest 1m 35s"
    assert [c["value"] for c in out["empty"]] == ["0", "none yet", "0", "0"]
    assert out["url"] == "https://bot.test/api/stats/o/r"
    assert out["list"] == "https://bot.test/api/stats"
    assert "token" in out["problems"][0] and "turned off" in out["problems"][1]
    assert "Sign in" in out["problems"][0] and "push" in out["problems"][3]
    assert out["login"] == ("https://bot.test/auth/login?return_to="
                            "https%3A%2F%2Fdash.test%2Fdashboard.html%3Fx%3D1")
    assert out["me"] == "https://bot.test/auth/me"
    assert out["bare"] == {"credentials": "include", "headers": {}}
    assert out["withToken"]["headers"] == {"Authorization": "Bearer t0k"}
