"""GitHub sign-in for the dashboard.

The README's Website section has maintainers "sign in with GitHub to see"
their repos' numbers. ``OAuthApp`` runs GitHub's OAuth web flow: it builds the
authorize URL, trades the returned code for a user token, and asks GitHub who
the user is and whether they can push to a repo. ``Sessions`` remembers who
signed in, in memory only, so user tokens never reach the state file; after a
restart people sign in again.
"""

from __future__ import annotations

import secrets
import time
from typing import Callable, Dict, Optional
from urllib.parse import urlencode

import httpx

from .github import API_URL, GitHubError

WEB_URL = "https://github.com"
# Reading which repos a user can push to needs no scope on public repos;
# ``repo`` would let the bot write to them, so ask for nothing more than this.
SCOPE = "read:user"
# A sign-in lasts a day; an unanswered login link lasts ten minutes.
SESSION_TTL = 24 * 3600
STATE_TTL = 600
_ACCEPT = "application/vnd.github+json"


class OAuthApp:
    def __init__(self, client_id: str, client_secret: str,
                 http: Optional[httpx.Client] = None,
                 web_url: str = WEB_URL, api_url: str = API_URL):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http or httpx.Client(timeout=10)
        self.web_url = web_url.rstrip("/")
        self.api_url = api_url.rstrip("/")

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        query = urlencode({"client_id": self.client_id, "redirect_uri": redirect_uri,
                           "scope": SCOPE, "state": state, "allow_signup": "false"})
        return f"{self.web_url}/login/oauth/authorize?{query}"

    def exchange(self, code: str, redirect_uri: str) -> str:
        """Trade the code GitHub sent back for a user token."""
        res = self.http.post(f"{self.web_url}/login/oauth/access_token",
                             headers={"Accept": "application/json"},
                             data={"client_id": self.client_id,
                                   "client_secret": self.client_secret,
                                   "code": code, "redirect_uri": redirect_uri})
        data = res.json() if res.status_code == 200 else {}
        # GitHub answers 200 with an "error" field when the code is bad.
        if "access_token" not in data:
            raise GitHubError(res.status_code, data.get("error", res.text))
        return data["access_token"]

    def _get(self, token: str, path: str) -> httpx.Response:
        return self.http.get(self.api_url + path, headers={
            "Authorization": f"token {token}", "Accept": _ACCEPT})

    def login(self, token: str) -> str:
        res = self._get(token, "/user")
        if res.status_code != 200:
            raise GitHubError(res.status_code, res.text)
        return res.json()["login"]

    def can_push(self, token: str, repo: str) -> bool:
        """Whether the token's user has write or admin access to ``repo``."""
        res = self._get(token, f"/repos/{repo}")
        if res.status_code != 200:
            return False
        return bool(res.json().get("permissions", {}).get("push"))


class Sessions:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._sessions: Dict[str, dict] = {}
        self._states: Dict[str, tuple] = {}

    def _prune(self) -> None:
        now = self.clock()
        for table in (self._sessions, self._states):
            for key in [k for k, v in table.items() if self._expires(v) <= now]:
                del table[key]

    @staticmethod
    def _expires(value) -> float:
        return value["expires"] if isinstance(value, dict) else value[1]

    def new_state(self, return_to: str) -> str:
        """A one-time value for the login link, remembering where to go after."""
        self._prune()
        state = secrets.token_urlsafe(24)
        self._states[state] = (return_to, self.clock() + STATE_TTL)
        return state

    def take_state(self, state: str) -> Optional[str]:
        """The ``return_to`` for a state, once; None if unknown or expired."""
        self._prune()
        entry = self._states.pop(state or "", None)
        return entry[0] if entry else None

    def start(self, login: str, token: str) -> str:
        self._prune()
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = {"login": login, "token": token,
                               "expires": self.clock() + SESSION_TTL, "push": {}}
        return sid

    def get(self, sid: Optional[str]) -> Optional[dict]:
        self._prune()
        return self._sessions.get(sid or "")

    def end(self, sid: Optional[str]) -> None:
        self._sessions.pop(sid or "", None)
