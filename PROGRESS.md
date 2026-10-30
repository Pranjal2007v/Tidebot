STATUS: IN PROGRESS

# Tidebot build progress

The spec is [README.md](README.md). Work follows its [Roadmap](README.md#roadmap) in order.

## Run 1 (2026-10-28)

**Estimated complete:** 5%

**Added**

- Python package skeleton (`pyproject.toml`, `.gitignore` keeping `.env`, `*.pem` and `state.json` out of git) and `tidebot/webhook.py`, which verifies the `X-Hub-Signature-256` HMAC on webhook deliveries.
- `tidebot/commands.py`: parses `:tide /command args` lines and a bare `/lgtm` from comment bodies, skipping code fences and quoted lines, with the command list from the README's [Commands](README.md#commands) section.
- `tidebot/config.py`: loads `.tide.yml` (see [Configuration](README.md#configuration)) with safe defaults for missing, unknown or mistyped keys.

**Next 5%**

- Permission tiers from [Permissions](README.md#permissions): map a GitHub permission level and star status to Anyone / Collaborator / Maintainer, and which commands each tier may run.
- Rate limiter (10 commands per hour per user, 50 per repo) with state saved to `state.json`.
- Router that ties parse → permission → rate limit together and returns what to do, plus a FastAPI receiver endpoint.

**Blockers:** none.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | Pranjal2007v | pranjalgangwar910@gmail.com | `81827ce15d495ed27edd4545acd0ca4afc88c798` | feat: add package skeleton and webhook signature verification |
| B | ishitasharma2490 | ishitasharma2490@gmail.com | `e896ba3be52846557021b32337c7aa20519dd4f9` | feat: parse :tide commands and bare /lgtm from comments |
| C | bitflicker64 | himnshuverma10152006@gmail.com | `49da75cb268398e899381fc9e629047d32995384` | feat: load .tide.yml config and start PROGRESS.md |

## Run 2 (2026-10-29)

**Estimated complete:** 10%

**Added**

- `tidebot/permissions.py`: the Anyone / Collaborator / Maintainer tiers from [Permissions](README.md#permissions), mapped from GitHub permission levels, with a required tier for every command and the optional star gate. `/assign` to yourself needs a collaborator, assigning others needs a maintainer. Commands the README doesn't place are put in a tier by risk: state changes (`/reopen`, `/retitle`, `/duplicate`, `/ship`) need a maintainer, `/cc` a collaborator, `/kudos`, `/size`, `/ping` and `/joke` anyone.
- `tidebot/state.py` and `tidebot/ratelimit.py`: one JSON state file written atomically, and sliding-window limits of 10 commands per hour per user (per repo) and 50 per repo. Denied commands don't count.
- `tidebot/router.py` and `tidebot/app.py`: the router (parse, permission check, rate limit, skip bots) and a FastAPI receiver with `POST /webhook` and `GET /healthz`. It answers `issue_comment` deliveries with the routing result as JSON. Permission comes from the comment's `author_association` for now.

**Next 5%**

- A small GitHub API client using a GitHub App installation token: post comments, add and remove labels, look up a user's real permission level and star status, and fetch `.tide.yml`.
- Wire the receiver to reply with the denial reason and run the first workflow commands: `/label`, `/close`, `/reopen`, `/assign`, `/cc`.
- `/help` reply listing the commands the caller's tier may run.

**Blockers:** none.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | ishitasharma2490 | ishitasharma2490@gmail.com | `23e5e83f65138f476be7b125271d6b3914484734` | feat: add permission tiers and per-command access checks |
| B | bitflicker64 | himnshuverma10152006@gmail.com | `b13b23e6bd5629eec4758e669c2bda309744c6e3` | feat: add hourly rate limits with state kept in state.json |
| C | Pranjal2007v | pranjalgangwar910@gmail.com | `bbc6f9e816da8c167b2febd6429ac62b8e7a988d` | feat: route comments and receive webhooks with FastAPI |
