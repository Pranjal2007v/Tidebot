"""Checks on the Dockerfile that don't need Docker itself."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def instruction(name):
    """The arguments of every ``name`` instruction, continuation lines joined."""
    text = re.sub(r"\\\n\s*", " ", DOCKERFILE)
    return [line.split(None, 1)[1] for line in text.splitlines()
            if line.split(None, 1)[:1] == [name]]


def test_runs_uvicorn_on_the_exposed_port():
    cmd = json.loads(instruction("CMD")[-1])
    assert cmd[:2] == ["uvicorn", "tidebot.app:app"]
    port = cmd[cmd.index("--port") + 1]
    assert instruction("EXPOSE") == [port]


def test_health_check_calls_the_health_route():
    from tidebot.app import create_app
    from tidebot.state import StateStore

    check = instruction("HEALTHCHECK")[0]
    assert "/healthz" in check
    paths = {route.path for route in create_app("s", StateStore(None)).routes}
    assert "/healthz" in paths


def test_runs_as_a_user_that_is_not_root():
    users = instruction("USER")
    assert users and users[-1] not in ("root", "0")


def test_state_lives_on_the_volume():
    assert "TIDEBOT_STATE=/data/state.json" in " ".join(instruction("ENV"))
    assert instruction("VOLUME") == ["/data"]


def test_installs_the_server_extra():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^serve = \["uvicorn', pyproject, re.M)
    assert any('".[serve]"' in run for run in instruction("RUN"))


def test_secrets_and_state_stay_out_of_the_image():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for name in (".env", "*.pem", "state.json", ".git"):
        assert name in ignored
