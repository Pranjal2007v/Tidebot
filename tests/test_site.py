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
