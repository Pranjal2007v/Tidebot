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

## Run 3 (2026-10-30)

**Estimated complete:** 15%

**Added**

- `tidebot/github.py`: a small REST client for the GitHub App. `AppAuth` signs an RS256 JWT with the App key and caches installation tokens until a minute before they expire. `GitHubClient` posts comments, adds and removes labels, opens and closes issues, assigns people, requests reviewers, reads a user's permission level (`role_name`, so triage and maintain are told apart), checks stars and fetches `.tide.yml`. `httpx` and `PyJWT[crypto]` are now runtime dependencies.
- `tidebot/workflow.py`: handlers for `/label` (`-name` removes a label), `/close`, `/reopen`, `/assign` (no target or `me` means the author) and `/cc` (requests a review on a PR, mentions on an issue).
- `tidebot/help.py` and the receiver wiring in `tidebot/app.py`: `/help` lists the commands the caller's tier may run, grouped as in [Commands](README.md#commands). With `TIDEBOT_APP_ID` and `TIDEBOT_PRIVATE_KEY` set, the receiver looks up the author's real permission and the repo's config, checks stars only when the star gate matters, runs the commands above and posts one reply holding `/help` output, denial reasons and API failures. Without credentials it behaves as before.

**Next 5%**

- `/lgtm`, `/hold` and `/wip` as labels (`lgtm`, `do-not-merge/hold`, `do-not-merge/wip`), with `/hold cancel` and `/wip cancel` to remove them.
- `/retitle`, `/lock`, `/milestone` and `/duplicate #N` (close with a link and a `duplicate` label).
- `/approve` and `/merge`: approve the PR, and merge only when CI is green and it has an approval, per [Commands](README.md#commands).

**Blockers:** none. Nothing has run against a live GitHub App yet; the API client is covered by mocked HTTP tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | bitflicker64 | himnshuverma10152006@gmail.com | `2b3db8d9340153b4838301a5e9c6799b3a37e30f` | feat: add GitHub API client with App installation tokens |
| B | Pranjal2007v | pranjalgangwar910@gmail.com | `9cb9f3d621a47e80330c90ecea2a94071a3d164c` | feat: run /label, /close, /reopen, /assign and /cc through the API |
| C | ishitasharma2490 | ishitasharma2490@gmail.com | *(this commit, filled in next run)* | feat: reply to commands on GitHub and add /help |
