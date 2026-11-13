# Setting up Tidebot

This guide sets up your own copy of the bot: a GitHub App, a server that runs it, and (if you want them) AI commands and the dashboard. One server can run the bot for every repo the App is installed on. Each repo then picks its options in a `.tide.yml`, as the README's [Configuration](../README.md#configuration) section describes.

## 1. Pick the bot's address

GitHub has to reach the bot over HTTPS. The README's [Architecture](../README.md#architecture) section runs it behind a Cloudflare tunnel, so the server needs no open ports. Any HTTPS address that forwards to port 8000 works. This guide calls it `https://bot.example.com`.

## 2. Create the GitHub App

Go to **Settings > Developer settings > GitHub Apps > New GitHub App** (for an organization: the organization's settings) and fill in:

- **Webhook URL:** `https://bot.example.com/webhook`
- **Webhook secret:** a long random string. Keep it for `TIDEBOT_WEBHOOK_SECRET`.
- **Callback URL:** `https://bot.example.com/auth/callback`. Only needed for dashboard sign-in. Leave "Request user authorization (OAuth) during installation" off.

### Repository permissions

| Permission | Access | What the bot uses it for |
|---|---|---|
| Issues | Read and write | comments, labels, assignees, milestones, closing, locking |
| Pull requests | Read and write | reviewers, inline reviews, approvals, changed files |
| Contents | Read and write | reading `.tide.yml` and changed files; write only for `/merge` |
| Checks | Read-only | whether CI passed before `/merge` |
| Commit statuses | Read-only | the same, for CI that reports statuses |
| Metadata | Read-only | required by GitHub; also the commenter's permission level |

Leave every other permission at "No access".

### Subscribe to events

- **Issues**
- **Issue comment**
- **Pull request**

Create the App, then on its settings page:

1. Note the **App ID** for `TIDEBOT_APP_ID`.
2. Under **Private keys**, generate a key and save the `.pem` file on the server. Never commit it; `.gitignore` already skips `*.pem`.
3. For dashboard sign-in, note the **Client ID** and generate a **client secret** for `TIDEBOT_GITHUB_CLIENT_ID` and `TIDEBOT_GITHUB_CLIENT_SECRET`.

## 3. Fill in the settings

Copy [`.env.example`](../.env.example) to `.env` and fill it in. It lists every setting with a line on what it does. Only `TIDEBOT_WEBHOOK_SECRET` is required; each group you leave empty keeps that feature off. With Docker, point `TIDEBOT_PRIVATE_KEY` at the path the key is mounted on, such as `/run/secrets/app.pem`.

Check the settings before starting:

```bash
python -m tidebot.doctor
```

It prints one line per feature (on, off or error) and exits with status 1 if anything is set up wrongly. It never prints a secret.

## 4. Run the bot

With Docker:

```bash
docker build -t tidebot .
docker run -d --name tidebot --restart unless-stopped --env-file .env \
  -v tidebot-data:/data -v "$PWD/app.pem:/run/secrets/app.pem:ro" \
  -p 127.0.0.1:8000:8000 tidebot
```

The state file lives on the `tidebot-data` volume, so it survives a rebuild. To check settings inside the container, run `docker run --rm --env-file .env tidebot python -m tidebot.doctor`.

Without Docker:

```bash
pip install ".[serve]"
set -a; . ./.env; set +a
uvicorn tidebot.app:app --host 127.0.0.1 --port 8000 --proxy-headers
```

`GET /healthz` answers with `"ok": true` once the bot is up. Its `ai` part says whether AI commands are on and how many AI jobs are waiting or running (`queued`), which shows when the model can't keep up.

## 5. Install it on a repo

On the App's page, choose **Install App** and pick the repos. GitHub sends a `ping` delivery, which the App's **Advanced** tab shows as delivered. Then comment `:tide /help` on any issue or PR.

## 6. The dashboard (optional)

The dashboard is the static `site/` folder. Host it anywhere, add its site (such as `https://tidebot.example.com`) to `TIDEBOT_DASHBOARD_ORIGINS`, and restart the bot. Maintainers sign in with GitHub and see numbers only for repos they can push to. To read every repo with one token instead, set `TIDEBOT_STATS_TOKEN` and paste it into the dashboard's token box.
