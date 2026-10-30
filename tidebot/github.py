"""A small client for the parts of the GitHub REST API Tidebot uses.

Tidebot runs as a GitHub App. ``AppAuth`` signs a short-lived JWT with the
App's private key and trades it for an installation token, which it caches
until shortly before it expires. ``GitHubClient`` takes a function that
returns a token, so tests can pass a fixed string instead.
"""

from __future__ import annotations

import calendar
import time
from typing import Callable, Dict, Iterable, Optional, Tuple

import httpx
import jwt

API_URL = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"
# Refresh a cached installation token this many seconds before it expires.
_TOKEN_MARGIN = 60
# How many pages of a user's stars to read before giving up on the star check.
_STAR_PAGES = 10


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API returned {status}: {message}")
        self.status = status


class AppAuth:
    def __init__(self, app_id: str, private_key: str, http: Optional[httpx.Client] = None,
                 base_url: str = API_URL, clock: Callable[[], float] = time.time):
        self.app_id = str(app_id)
        self.private_key = private_key
        self.http = http or httpx.Client(timeout=10)
        self.base_url = base_url.rstrip("/")
        self.clock = clock
        self._tokens: Dict[int, Tuple[str, float]] = {}

    def app_jwt(self) -> str:
        # GitHub allows at most 10 minutes; backdate a little for clock drift.
        now = int(self.clock())
        claims = {"iat": now - 60, "exp": now + 540, "iss": self.app_id}
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    def installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] - _TOKEN_MARGIN > self.clock():
            return cached[0]
        res = self.http.post(
            f"{self.base_url}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self.app_jwt()}", "Accept": _ACCEPT,
                     "X-GitHub-Api-Version": _API_VERSION},
        )
        if res.status_code != 201:
            raise GitHubError(res.status_code, res.text)
        data = res.json()
        # Tokens last an hour; if the expiry is missing, assume that.
        expires = _parse_time(data.get("expires_at")) or self.clock() + 3600
        self._tokens[installation_id] = (data["token"], expires)
        return data["token"]


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return None


class GitHubClient:
    def __init__(self, token: Callable[[], str], http: Optional[httpx.Client] = None,
                 base_url: str = API_URL):
        self.token = token
        self.http = http or httpx.Client(timeout=10)
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, ok: Iterable[int] = (200, 201, 204),
                 accept: str = _ACCEPT, **kwargs) -> httpx.Response:
        res = self.http.request(method, self.base_url + path, headers={
            "Authorization": f"token {self.token()}",
            "Accept": accept,
            "X-GitHub-Api-Version": _API_VERSION,
        }, **kwargs)
        if res.status_code not in ok:
            raise GitHubError(res.status_code, res.text)
        return res

    def post_comment(self, repo: str, number: int, body: str) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body})

    def add_labels(self, repo: str, number: int, labels: Iterable[str]) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/labels",
                      json={"labels": list(labels)})

    def remove_label(self, repo: str, number: int, label: str) -> None:
        # A label that isn't on the issue is already removed.
        self._request("DELETE", f"/repos/{repo}/issues/{number}/labels/{label}",
                      ok=(200, 204, 404))

    def set_state(self, repo: str, number: int, state: str) -> None:
        """Set an issue or PR to ``open`` or ``closed``."""
        self._request("PATCH", f"/repos/{repo}/issues/{number}", json={"state": state})

    def add_assignees(self, repo: str, number: int, logins: Iterable[str]) -> None:
        self._request("POST", f"/repos/{repo}/issues/{number}/assignees",
                      json={"assignees": list(logins)})

    def request_reviewers(self, repo: str, number: int, logins: Iterable[str]) -> None:
        self._request("POST", f"/repos/{repo}/pulls/{number}/requested_reviewers",
                      json={"reviewers": list(logins)})

    def permission(self, repo: str, login: str) -> Optional[str]:
        """Return ``login``'s permission level on ``repo``, or None if they have none."""
        res = self._request("GET", f"/repos/{repo}/collaborators/{login}/permission",
                            ok=(200, 404))
        if res.status_code == 404:
            return None
        data = res.json()
        # ``role_name`` tells triage and maintain apart; ``permission`` folds
        # them into read and write.
        return data.get("role_name") or data.get("permission")

    def has_starred(self, login: str, repo: str) -> bool:
        """Check whether ``login`` has starred ``repo``.

        GitHub has no direct check for another user, so this pages through
        their stars and stops after a few pages.
        """
        wanted = repo.lower()
        for page in range(1, _STAR_PAGES + 1):
            res = self._request("GET", f"/users/{login}/starred",
                                params={"per_page": 100, "page": page})
            repos = res.json()
            if any(r.get("full_name", "").lower() == wanted for r in repos):
                return True
            if len(repos) < 100:
                return False
        return False

    def fetch_file(self, repo: str, path: str) -> Optional[str]:
        """Return the text of ``path`` on the default branch, or None if it's missing."""
        res = self._request("GET", f"/repos/{repo}/contents/{path}", ok=(200, 404),
                            accept="application/vnd.github.raw+json")
        return None if res.status_code == 404 else res.text
