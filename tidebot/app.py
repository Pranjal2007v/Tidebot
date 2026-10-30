"""The FastAPI receiver for GitHub webhooks.

It verifies the delivery signature, routes new issue and PR comments, and
returns the routing result as JSON. When it has GitHub App credentials it
also acts: it looks up the author's real permission and the repo's
``.tide.yml``, runs the workflow commands it knows, and posts one reply with
``/help`` output and the reason for any denied command.

Run it with ``uvicorn tidebot.app:app`` and ``TIDEBOT_WEBHOOK_SECRET`` set.
Set ``TIDEBOT_APP_ID`` and ``TIDEBOT_PRIVATE_KEY`` (the path to the App's
``.pem`` file) to let it reply.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Request

from .config import CONFIG_PATH, TideConfig, parse_config
from .github import AppAuth, GitHubClient, GitHubError
from .help import help_text
from .permissions import Tier, tier_for
from .ratelimit import RateLimiter
from .router import Action, route_comment
from .state import DEFAULT_PATH, StateStore
from .webhook import verify_signature
from .workflow import Target, run_command

# Until the bot looks up real permission levels through the API, the
# ``author_association`` GitHub puts on every comment is a close stand-in.
_ASSOCIATION_PERMISSIONS = {
    "OWNER": "admin",
    "MEMBER": "write",
    "COLLABORATOR": "triage",
}

PermissionLookup = Callable[[str, dict], Optional[str]]
# Given an installation id, return a client that acts as that installation.
ClientFactory = Callable[[int], GitHubClient]


def permission_from_association(repo: str, comment: dict) -> Optional[str]:
    return _ASSOCIATION_PERMISSIONS.get(comment.get("author_association", ""))


def _reply_for(gh: GitHubClient, target: Target, action: Action,
               permission: Optional[str]) -> Optional[str]:
    name = action.command.name
    if not action.allowed:
        return f"`/{name}`: {action.reason}"
    if name == "help":
        return help_text(target.author, permission)
    try:
        return run_command(gh, target, action.command)
    except GitHubError as err:
        return f"`/{name}` failed: GitHub answered {err.status}"


def create_app(secret: str, store: StateStore,
               permission_lookup: PermissionLookup = permission_from_association,
               github: Optional[ClientFactory] = None) -> FastAPI:
    app = FastAPI(title="Tidebot")
    limiter = RateLimiter(store)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/webhook")
    async def webhook(request: Request):
        body = await request.body()
        if not verify_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
            raise HTTPException(status_code=401, detail="bad signature")
        event = request.headers.get("X-GitHub-Event", "")
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(status_code=400, detail="body is not JSON")

        if event == "ping":
            return {"ok": True, "actions": []}
        if event != "issue_comment" or payload.get("action") != "created":
            return {"ok": True, "ignored": event, "actions": []}

        repo = payload.get("repository", {}).get("full_name", "")
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        author = comment.get("user", {}).get("login", "")
        installation = payload.get("installation", {}).get("id")
        gh = github(installation) if github and installation else None

        config, starred = TideConfig(), False
        if gh is None:
            permission = permission_lookup(repo, comment)
        else:
            permission = gh.permission(repo, author)
            config = parse_config(gh.fetch_file(repo, CONFIG_PATH))
            # Paging through stars is slow, so only do it when it matters.
            if config.star_gate and tier_for(permission) == Tier.ANYONE:
                starred = gh.has_starred(author, repo)

        actions = route_comment(repo, author, comment.get("body"), permission, limiter,
                                config, starred)
        replied = False
        if gh is not None and actions and "number" in issue:
            target = Target(repo, issue["number"], "pull_request" in issue, author)
            replies = [r for r in (_reply_for(gh, target, a, permission) for a in actions) if r]
            if replies:
                gh.post_comment(repo, target.number, "\n\n".join(replies))
                replied = True
        return {"ok": True, "replied": replied, "actions": [
            {"command": a.command.name, "args": a.command.args,
             "allowed": a.allowed, "reason": a.reason}
            for a in actions
        ]}

    return app


def _github_from_env() -> Optional[ClientFactory]:
    app_id = os.environ.get("TIDEBOT_APP_ID")
    key_path = os.environ.get("TIDEBOT_PRIVATE_KEY")
    if not app_id or not key_path:
        return None
    with open(key_path, encoding="utf-8") as fh:
        auth = AppAuth(app_id, fh.read())
    return lambda installation: GitHubClient(lambda: auth.installation_token(installation))


def _app_from_env() -> FastAPI:
    return create_app(os.environ.get("TIDEBOT_WEBHOOK_SECRET", ""),
                      StateStore(os.environ.get("TIDEBOT_STATE", DEFAULT_PATH)),
                      github=_github_from_env())


app = _app_from_env()
