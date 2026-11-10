"""The FastAPI receiver for GitHub webhooks.

It verifies the delivery signature, routes new issue and PR comments, and
returns the routing result as JSON. When it has GitHub App credentials it
also acts: it looks up the author's real permission and the repo's
``.tide.yml``, runs the commands it knows, posts one reply with ``/help``
output and the reason for any denied command, posts ``/remind``
reminders once they are due, and handles new pull requests as the README's
Automatic behavior section describes: new PRs and issues, and comments
asking to work on an issue. AI commands go to the AI queue, and each posts
its own answer when the model is done.

Run it with ``uvicorn tidebot.app:app`` and ``TIDEBOT_WEBHOOK_SECRET`` set.
Set ``TIDEBOT_APP_ID`` and ``TIDEBOT_PRIVATE_KEY`` (the path to the App's
``.pem`` file) to let it reply, and the ``TIDEBOT_AI_*`` variables described
in ``tidebot/ai.py`` to turn on AI commands. Set ``TIDEBOT_STATS_TOKEN`` to
serve per-repo numbers at ``/api/stats/<owner>/<repo>`` to callers that send it
as a bearer token.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from functools import partial
from typing import Callable, Optional

from fastapi import FastAPI, Header, HTTPException, Request

from .ai import NOT_CONFIGURED, ai_from_env
from .aicommands import AI_HANDLERS, make_job, usage_error
from .aiqueue import AIQueue, waiting_note
from .community import Community
from .config import CONFIG_PATH, TideConfig, parse_config
from .events import (claim_issue, issue_opened, pull_request_opened, pull_request_pushed,
                     pull_request_ready)
from .github import AppAuth, GitHubClient, GitHubError
from .help import help_text
from .metrics import Metrics
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
# How often to look for reminders that are due, in seconds.
REMINDER_INTERVAL = 60
# (event, action) pairs Tidebot answers automatically, with the payload key
# holding the PR or issue and the handler to run.
_EVENT_HANDLERS = {
    ("pull_request", "opened"): ("pull_request", pull_request_opened),
    ("pull_request", "synchronize"): ("pull_request", pull_request_pushed),
    ("pull_request", "ready_for_review"): ("pull_request", pull_request_ready),
    ("issues", "opened"): ("issue", issue_opened),
}


def permission_from_association(repo: str, comment: dict) -> Optional[str]:
    return _ASSOCIATION_PERMISSIONS.get(comment.get("author_association", ""))


def _reply_for(gh: GitHubClient, target: Target, action: Action,
               permission: Optional[str], community: Community,
               ai: Optional[AIQueue], metrics: Metrics) -> Optional[str]:
    name = action.command.name
    if not action.allowed:
        return f"`/{name}`: {action.reason}"
    if name == "help":
        return help_text(target.author, permission)
    if name in AI_HANDLERS:
        usage = usage_error(action.command)
        if usage or ai is None:
            return usage or f"`/{name}`: {NOT_CONFIGURED}"
        return waiting_note(name, ai.submit(make_job(gh, target, action.command,
                                                   metrics.record_reply),
                                                  target.repo))
    try:
        if community.handles(name):
            return community.run(gh, target, action.command)
        return run_command(gh, target, action.command)
    except GitHubError as err:
        return f"`/{name}` failed: GitHub answered {err.status}"


def create_app(secret: str, store: StateStore,
               permission_lookup: PermissionLookup = permission_from_association,
               github: Optional[ClientFactory] = None,
               reminder_interval: float = REMINDER_INTERVAL,
               ai: Optional[AIQueue] = None,
               stats_token: Optional[str] = None) -> FastAPI:
    limiter = RateLimiter(store)
    community = Community(store)
    metrics = Metrics(store)
    if ai is not None and ai.on_wait is None:
        ai.on_wait = metrics.record_wait
    # New issues may queue an AI check on borderline duplicates.
    opened = partial(issue_opened, ai=ai, on_duplicates=metrics.record_duplicates)
    event_handlers = {**_EVENT_HANDLERS, ("issues", "opened"): ("issue", opened)}

    def deliver_reminders() -> None:
        try:
            community.reminders.deliver_due(github)
        except Exception as err:  # keep the loop alive; the next round retries
            print(f"tidebot: delivering reminders failed: {err!r}")

    async def reminder_loop() -> None:
        while True:
            await asyncio.sleep(reminder_interval)
            deliver_reminders()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if github is None:
            yield
            return
        # Catch up on anything that came due while the bot was down.
        deliver_reminders()
        task = asyncio.create_task(reminder_loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="Tidebot", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/stats/{owner}/{name}")
    def repo_stats(owner: str, name: str, authorization: Optional[str] = Header(None)):
        # Off unless a token is set; the dashboard's GitHub sign-in comes later.
        if not stats_token:
            raise HTTPException(status_code=404, detail="stats are turned off")
        if not hmac.compare_digest(authorization or "", f"Bearer {stats_token}"):
            raise HTTPException(status_code=401, detail="bad token")
        return metrics.report(f"{owner}/{name}")

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

        repo = payload.get("repository", {}).get("full_name", "")
        installation = payload.get("installation", {}).get("id")
        gh = github(installation) if github and installation else None

        handled = event_handlers.get((event, payload.get("action", "")))
        if handled and gh is not None:
            key, handler = handled
            item = payload.get(key, {})
            if "number" in item:
                config = parse_config(gh.fetch_file(repo, CONFIG_PATH))
                try:
                    handler(gh, repo, item, config)
                except GitHubError as err:
                    print(f"tidebot: handling {event} {repo}#{item['number']} failed: {err}")
                return {"ok": True, "handled": event, "actions": []}
        if event != "issue_comment" or payload.get("action") != "created":
            return {"ok": True, "ignored": event, "actions": []}

        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        author = comment.get("user", {}).get("login", "")

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
        for action in actions:
            if action.allowed:
                community.record(repo, action.command.name)
        replied = False
        if gh is not None and "number" in issue:
            target = Target(repo, issue["number"], "pull_request" in issue, author,
                            installation)
            replies = [r for r in (_reply_for(gh, target, a, permission, community, ai,
                                                  metrics)
                                       for a in actions) if r]
            claimed = claim_issue(gh, repo, issue, author, comment.get("body"))
            if claimed:
                replies.append(claimed)
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
    model = ai_from_env()
    return create_app(os.environ.get("TIDEBOT_WEBHOOK_SECRET", ""),
                      StateStore(os.environ.get("TIDEBOT_STATE", DEFAULT_PATH)),
                      github=_github_from_env(),
                      ai=AIQueue(model) if model else None,
                      stats_token=os.environ.get("TIDEBOT_STATS_TOKEN"))


app = _app_from_env()
