"""Generate the website's command reference and config builder.

The command reference comes from the command catalog and the config builder
from the switches in ``tidebot/config.py``. Run ``python -m tidebot.sitegen``
after changing a command, its tier, its catalog entry or a config option. A
test fails when ``site/commands.html`` or ``site/config.html`` is out of date.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import List

from .catalog import Entry, entries, tiers
from .commands import Command
from .config import TideConfig, options, to_yaml
from .permissions import required_tier

SITE = Path(__file__).resolve().parent.parent / "site"
OUTPUT = SITE / "commands.html"
CONFIG_OUTPUT = SITE / "config.html"

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def inline(text: str) -> str:
    """Escape ``text`` and turn `code` and **bold** into HTML."""
    out = html.escape(text, quote=False)
    out = _CODE.sub(r"<code>\1</code>", out)
    return _BOLD.sub(r"<strong>\1</strong>", out)


def _row(entry: Entry) -> List[str]:
    search = " ".join([entry.name, entry.group, entry.tier, entry.summary]).lower()
    # The lowest tier that can run the command at all, for the tier filter.
    level = int(required_tier(Command(entry.name), ""))
    bare = (f'<p class="note">Collaborators can also write a bare <code>/{entry.name}</code> '
            "on its own line.</p>") if entry.bare else ""
    return [
        f'      <article class="command" id="{entry.name}" data-level="{level}" '
        f'data-search="{html.escape(search)}">',
        f'        <h3><a href="#{entry.name}">/{entry.name}</a> '
        f'<span class="tier">{html.escape(entry.tier)}</span></h3>',
        f"        <p>{inline(entry.summary)}</p>",
        f"        <pre><code>{html.escape(entry.example, quote=False)}</code></pre>",
        f'        <p class="result">{inline(entry.result)}</p>',
        *([f"        {bare}"] if bare else []),
        "      </article>",
    ]


def _head(title: str, description: str) -> List[str]:
    """The top of a generated page, up to the start of ``<main>``."""
    return [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"  <title>{html.escape(title)}</title>",
        f'  <meta name="description" content="{html.escape(description)}">',
        '  <link rel="stylesheet" href="style.css">',
        "</head>",
        "<body>",
        '  <header class="top">',
        '    <div class="wrap">',
        '      <a class="brand" href="index.html">Tidebot</a>',
        "      <nav>",
        '        <a href="commands.html">Commands</a>',
        '        <a href="config.html">Config</a>',
        '        <a href="https://github.com/Pranjal2007v/Tidebot">GitHub</a>',
        "      </nav>",
        "    </div>",
        "  </header>",
        "",
    ]


def render() -> str:
    all_entries = entries()
    lines = [
        *_head("Tidebot commands", "Every Tidebot command, who can run it and an example."),
        '  <main class="wrap">',
        '    <div class="hero">',
        "      <h1>Commands</h1>",
        f"      <p>{len(all_entries)} commands in three groups. Start a line with "
        "<code>:tide</code>, then the command.</p>",
        "    </div>",
        '    <form class="filters" role="search" onsubmit="return false">',
        '      <label for="search">Search</label>',
        '      <input type="search" id="search" placeholder="merge, review, label..." autocomplete="off">',
        '      <label for="tier">Commands I can run as</label>',
        '      <select id="tier">',
        '        <option value="">show all</option>',
        *[f'        <option value="{i}">{name}</option>' for i, name in enumerate(tiers())],
        "      </select>",
        "    </form>",
        '    <p id="no-results" hidden>No command matches that search.</p>',
        "",
    ]
    group = None
    for entry in all_entries:
        if entry.group != group:
            if group is not None:
                lines += ["    </section>", ""]
            group = entry.group
            slug = group.lower()
            lines += [f'    <section class="group" id="group-{slug}">', f"      <h2>{group}</h2>"]
        lines += _row(entry)
    lines += [
        "    </section>",
        "  </main>",
        "",
        "  <footer>",
        '    <div class="wrap">Generated from the command list in the Tidebot source. '
        'See <a href="https://github.com/Pranjal2007v/Tidebot#permissions">Permissions</a> '
        "for what each tier means.</div>",
        "  </footer>",
        '  <script src="search.js"></script>',
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(lines)


def render_config() -> str:
    """The config builder: one switch per ``.tide.yml`` option and the YAML."""
    lines = [
        *_head("Tidebot config builder", "Pick Tidebot's options and copy the .tide.yml."),
        '  <main class="wrap">',
        '    <div class="hero">',
        "      <h1>Config builder</h1>",
        "      <p>Turn options on or off, then copy the result into <code>.tide.yml</code> "
        "at the root of your repo. Every option starts at its default.</p>",
        "    </div>",
        '    <div class="builder">',
        '      <form id="options" onsubmit="return false">',
    ]
    for option in options():
        checked = " checked" if option.default else ""
        default = "true" if option.default else "false"
        lines += [
            '        <label class="option">',
            f'          <input type="checkbox" id="{option.name}" name="{option.name}" '
            f'data-default="{default}"{checked}>',
            f"          <code>{option.name}</code>",
            f"          <span>{inline(option.help)}</span>",
            "        </label>",
        ]
    lines += [
        "      </form>",
        '      <div class="output">',
        '        <pre><code id="yaml">'
        + html.escape(to_yaml(TideConfig()), quote=False) + "</code></pre>",
        '        <button type="button" class="button" id="copy">Copy .tide.yml</button>',
        "      </div>",
        "    </div>",
        "  </main>",
        "",
        "  <footer>",
        '    <div class="wrap">Generated from the options in the Tidebot source. See '
        '<a href="https://github.com/Pranjal2007v/Tidebot#configuration">Configuration</a> '
        "for how the file is read.</div>",
        "  </footer>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(lines)


PAGES = {OUTPUT: render, CONFIG_OUTPUT: render_config}


def main(argv: List[str]) -> int:
    for path, build in PAGES.items():
        path.write_text(build(), encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
