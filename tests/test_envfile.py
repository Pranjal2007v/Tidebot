"""The sample env file lists every variable the bot reads, and only those."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READ = re.compile(r"""\.get\(\s*["'](TIDEBOT_[A-Z_]+)["']""")


def read_by_code():
    names = set()
    for path in (ROOT / "tidebot").glob("*.py"):
        names.update(READ.findall(path.read_text(encoding="utf-8")))
    return names


def listed():
    names = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line.split("=", 1)[0])
    return names


def test_code_reads_the_variables_we_expect():
    assert {"TIDEBOT_WEBHOOK_SECRET", "TIDEBOT_AI_URL", "TIDEBOT_PUBLIC_URL"} <= read_by_code()


def test_env_example_matches_the_code():
    assert set(listed()) == read_by_code()


def test_env_example_lists_each_variable_once():
    names = listed()
    assert len(names) == len(set(names))


def test_env_example_holds_no_secrets():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("TIDEBOT_") and line != "TIDEBOT_STATE=state.json":
            assert line.endswith("="), line


def test_real_env_file_is_ignored():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored
