"""Check a server's ``TIDEBOT_*`` settings before starting the bot.

``python -m tidebot.doctor`` reads the same variables as ``tidebot/app.py``
(``.env.example`` lists them), prints one line per feature saying whether it
is on, off or set up wrongly, and exits with status 1 when anything is wrong,
so a hosted setup can run it before starting the server. It never prints a
secret's value.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Mapping, NamedTuple
from urllib.parse import urlparse

ON, OFF, ERROR = "on", "off", "error"


class Check(NamedTuple):
    feature: str
    status: str
    message: str


def _get(env: Mapping[str, str], name: str) -> str:
    return env.get(name, "").strip()


def _missing(env: Mapping[str, str], names: List[str]) -> List[str]:
    return [n for n in names if not _get(env, n)]


def _group(env: Mapping[str, str], feature: str, names: List[str], on: str) -> Check:
    """On when every name is set, off when none is, an error when only some are."""
    missing = _missing(env, names)
    if not missing:
        return Check(feature, ON, on)
    if len(missing) == len(names):
        return Check(feature, OFF, "set " + ", ".join(names) + " to turn it on")
    return Check(feature, ERROR, "also set " + ", ".join(missing))


def _bad_origin(origin: str) -> bool:
    url = urlparse(origin)
    return url.scheme not in ("http", "https") or not url.netloc or url.path not in ("", "/")


def check(env: Mapping[str, str]) -> List[Check]:
    checks = []

    if _get(env, "TIDEBOT_WEBHOOK_SECRET"):
        checks.append(Check("webhook", ON, "deliveries are checked against the secret"))
    else:
        checks.append(Check("webhook", ERROR, "set TIDEBOT_WEBHOOK_SECRET; every delivery "
                                              "would be refused without it"))

    state = Path(_get(env, "TIDEBOT_STATE") or "state.json")
    folder = state.parent if str(state.parent) else Path(".")
    if folder.is_dir() and os.access(folder, os.W_OK):
        checks.append(Check("state", ON, f"kept in {state}"))
    else:
        checks.append(Check("state", ERROR, f"can't write to {folder}"))

    replies = _group(env, "replies", ["TIDEBOT_APP_ID", "TIDEBOT_PRIVATE_KEY"],
                     "the bot replies as the GitHub App")
    if replies.status == ON:
        key = Path(_get(env, "TIDEBOT_PRIVATE_KEY"))
        try:
            pem = key.read_text(encoding="utf-8")
        except OSError:
            replies = Check("replies", ERROR, f"can't read the private key at {key}")
        else:
            if "PRIVATE KEY-----" not in pem:
                replies = Check("replies", ERROR, f"{key} is not a .pem private key")
    checks.append(replies)

    ai = _group(env, "ai", ["TIDEBOT_AI_URL", "TIDEBOT_AI_MODEL"],
                "AI commands use " + _get(env, "TIDEBOT_AI_MODEL"))
    if ai.status == OFF and _get(env, "TIDEBOT_AI_KEY"):
        ai = Check("ai", ERROR, "TIDEBOT_AI_KEY is set but TIDEBOT_AI_URL and "
                                "TIDEBOT_AI_MODEL are not")
    checks.append(ai)

    if _get(env, "TIDEBOT_STATS_TOKEN"):
        checks.append(Check("stats token", ON, "the token can read every repo's numbers"))
    else:
        checks.append(Check("stats token", OFF, "set TIDEBOT_STATS_TOKEN to share every "
                                                "repo's numbers with one token"))

    origins = [o.strip() for o in _get(env, "TIDEBOT_DASHBOARD_ORIGINS").split(",") if o.strip()]
    bad = [o for o in origins if _bad_origin(o)]
    if bad:
        checks.append(Check("dashboard", ERROR, "not a site like https://example.com: "
                                                + ", ".join(bad)))
    elif origins:
        checks.append(Check("dashboard", ON, "the page on " + ", ".join(origins)
                                             + " may read the stats"))
    else:
        checks.append(Check("dashboard", OFF, "set TIDEBOT_DASHBOARD_ORIGINS to let a "
                                              "dashboard page on another site read the stats"))

    names = ["TIDEBOT_GITHUB_CLIENT_ID", "TIDEBOT_GITHUB_CLIENT_SECRET", "TIDEBOT_PUBLIC_URL"]
    public = _get(env, "TIDEBOT_PUBLIC_URL")
    signin = _group(env, "sign-in", names,
                    "callback is " + public.rstrip("/") + "/auth/callback")
    if signin.status == ON and not public.startswith("https://"):
        signin = Check("sign-in", ERROR, "TIDEBOT_PUBLIC_URL must start with https://, "
                                         "since the sign-in cookie is Secure")
    elif signin.status == ON and not origins:
        signin = Check("sign-in", ERROR, "sign-in only returns to a page in "
                                         "TIDEBOT_DASHBOARD_ORIGINS, which is empty")
    checks.append(signin)
    return checks


def main(env: Mapping[str, str] = os.environ, out=sys.stdout) -> int:
    checks = check(env)
    width = max(len(c.feature) for c in checks)
    for c in checks:
        print(f"{c.feature:<{width}}  {c.status:<5}  {c.message}", file=out)
    return 1 if any(c.status == ERROR for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
