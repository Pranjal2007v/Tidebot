"""Generate the website's command reference from the command catalog.

Run ``python -m tidebot.sitegen`` after changing a command, its tier or its
catalog entry. A test fails when ``site/commands.html`` is out of date.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import List

from .catalog import Entry, entries, tiers
from .commands import Command
from .permissions import required_tier

SITE = Path(__file__).resolve().parent.parent / "site"
OUTPUT = SITE / "commands.html"

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


def render() -> str:
    all_entries = entries()
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>Tidebot commands</title>",
        '  <meta name="description" content="Every Tidebot command, who can run it and an example.">',
        '  <link rel="stylesheet" href="style.css">',
        "</head>",
        "<body>",
        '  <header class="top">',
        '    <div class="wrap">',
        '      <a class="brand" href="index.html">Tidebot</a>',
        "      <nav>",
        '        <a href="commands.html">Commands</a>',
        '        <a href="https://github.com/Pranjal2007v/Tidebot">GitHub</a>',
        "      </nav>",
        "    </div>",
        "  </header>",
        "",
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


def main(argv: List[str]) -> int:
    OUTPUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
