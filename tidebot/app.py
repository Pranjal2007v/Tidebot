"""The FastAPI receiver for GitHub webhooks.

It verifies the delivery signature, routes new issue and PR comments, and
returns the routing result as JSON. Replying through the GitHub API comes
later; until then the response body shows what the bot would do.

Run it with ``uvicorn tidebot.app:app`` and ``TIDEBOT_WEBHOOK_SECRET`` set.
"""

from __future__ import annotations

import json
import os
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Request

from .ratelimit import RateLimiter
from .router import route_comment
from .state import DEFAULT_PATH, StateStore
from .webhook import verify_signature

# Until the bot looks up real permission levels through the API, the
# ``author_association`` GitHub puts on every comment is a close stand-in.
_ASSOCIATION_PERMISSIONS = {
    "OWNER": "admin",
    "MEMBER": "write",
    "COLLABORATOR": "triage",
}

PermissionLookup = Callable[[str, dict], Optional[str]]


def permission_from_association(repo: str, comment: dict) -> Optional[str]:
    return _ASSOCIATION_PERMISSIONS.get(comment.get("author_association", ""))


def create_app(secret: str, store: StateStore,
               permission_lookup: PermissionLookup = permission_from_association) -> FastAPI:
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
        author = comment.get("user", {}).get("login", "")
        actions = route_comment(repo, author, comment.get("body"),
                                permission_lookup(repo, comment), limiter)
        return {"ok": True, "actions": [
            {"command": a.command.name, "args": a.command.args,
             "allowed": a.allowed, "reason": a.reason}
            for a in actions
        ]}

    return app


def _app_from_env() -> FastAPI:
    return create_app(os.environ.get("TIDEBOT_WEBHOOK_SECRET", ""),
                      StateStore(os.environ.get("TIDEBOT_STATE", DEFAULT_PATH)))


app = _app_from_env()
