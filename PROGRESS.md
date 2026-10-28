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
| C | bitflicker64 | himnshuverma10152006@gmail.com | *(this commit, filled in next run)* | feat: load .tide.yml config and start PROGRESS.md |
