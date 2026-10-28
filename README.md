# Tidebot

**A maintainer's assistant for GitHub.** Tidebot is a GitHub App that handles the repetitive chores of running an open-source repo: labeling, duplicate checks, first-pass code review, reminders and merging, so maintainers can spend their time on the work that matters.

> Status: early development. The name "Tidebot" is a placeholder.

---
## Why Tidebot?

Maintainers lose hours every week to chores:

- Labeling every new issue, checking for duplicates, assigning it.
- Doing a first pass on every PR: size, missing description, obvious bugs.
- Assigning reviewers, placing holds, sending reminders, merging once CI is green.
- Replying to "can I work on this?" while new contributors wait for days.

Tidebot automates the routine parts and gives maintainers short commands for the rest.

## How it works

Talk to Tidebot with short commands in issues, PRs and Discussions:

```
:tide /review-sc
:tide /ask where is auth handled?
:tide /hold
```

The trigger is `:tide`, not an @mention, so nobody's GitHub account gets pinged by accident. Collaborators can also write a bare `/lgtm` on its own line, like Prow.

## Commands

About 45 commands in three groups.

### AI commands (14)

`/ask`, `/review`, `/review-sc` (posts inline suggested changes), `/security`, `/perf`, `/docs`, `/test`, `/summarize`, `/explain`, `/changelog`, `/estimate`, `/checklist`, `/roast`, `/chat`

### Workflow (about 20)

`/assign`, `/label`, `/close`, `/reopen`, `/retitle`, `/duplicate`, `/milestone`, `/lock`, `/cc`, `/lgtm`, `/hold`, `/wip`, `/approve`, `/merge` (needs CI and approval), `/ship`

### Community (about 10)

`/vote`, `/kudos`, `/stats`, `/remind 2h ...`, `/size`, `/ping`, `/joke`, `/help`

## Automatic behavior

**When a PR opens**, Tidebot:

- posts a welcome comment with the command list
- adds a `size/XS` to `size/XL` label
- lints the title and description
- assigns reviewers by code area

**When an issue opens**, Tidebot:

- labels it by content
- checks for duplicates among open issues, using TF-IDF similarity first and an AI check on borderline matches
- adds a `triage` label until a maintainer looks at it
- assigns the issue to anyone who comments "I'd like to work on this"

## How code review works

1. Read the whole PR thread and write a short memo on what the PR is trying to do.
2. Review each changed file on its own, four at a time, skipping lockfiles and generated code.
3. Check every suggestion against the real lines in the file. If a suggestion doesn't apply cleanly, it isn't posted.
4. Post up to 12 inline suggested changes and summarize the rest in a single comment.

## Permissions

| Tier | Who | Commands |
|---|---|---|
| Anyone | People who starred the repo (optional per repo) | AI commands, stats, help |
| Collaborator | Triage access | `/lgtm`, `/hold`, `/wip`, `/remind`, `/vote`, self-assign |
| Maintainer | Write or admin access | `/merge`, `/approve`, `/close`, `/label`, `/lock`, `/milestone`, assign others |

**Rate limits:** 10 commands per hour per user and 50 per repo. AI commands wait in a queue so a small server doesn't fall over.

## Configuration

Each repo sets its options in a `.tide.yml` file at the repo root. Configurable options include auto-labels, size labels, the star gate, the triage label and PR lint.

Example (key names are illustrative and may change):

```yaml
auto_label: true
size_labels: true
star_gate: false
triage_label: true
pr_lint: true
```

A web-based config builder is planned (see Roadmap).

## Architecture

```
GitHub webhook
  → HTTPS tunnel
  → receiver (verifies signature)
  → router (parses command, checks permission and rate limit)
  → AI queue
  → any OpenAI-compatible model
  → reply via GitHub API
```

- One Python (FastAPI) process, with state in a JSON file.
- Designed to run on a free-tier 1 GB VM with free model endpoints.
- Runs behind a Cloudflare tunnel, so no ports are open.
- Works with any OpenAI-compatible model endpoint.

## Website

A companion website is planned with four parts:

- **Landing page:** what the bot does, an example comment thread, and an "Install on GitHub" button.
- **Command reference:** every command with who can run it and an example of its output. Searchable.
- **Config builder:** toggle options and copy the generated `.tide.yml`.
- **Dashboard:** sign in with GitHub to see commands run, queue wait times, reviews posted and duplicates caught, per repo.

## Roadmap

- [ ] Core bot: webhooks, workflow commands, permission tiers
- [ ] AI commands, review pipeline, duplicate detection
- [ ] Website: landing page, command reference, config builder
- [ ] Dashboard
- [ ] Hosted option, so repos don't have to run it themselves

## Getting started

Setup instructions are coming soon. In short:

1. Install the Tidebot GitHub App on your repo.
2. Add a `.tide.yml` to configure it.
3. Comment `:tide /help` on any issue or PR.

## Contributing

Feedback is welcome, especially on the command list. If a command wouldn't be used by anyone, it should be cut. Open an issue to share your thoughts.

## License

To be decided.
