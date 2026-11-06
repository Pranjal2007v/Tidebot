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
| C | ishitasharma2490 | ishitasharma2490@gmail.com | `01785ca7b9057f5f42c99a6065f2d2f0bd16b8f6` | feat: reply to commands on GitHub and add /help |

## Run 4 (2026-10-31)

**Estimated complete:** 20%

**Added**

- `/lgtm`, `/hold` and `/wip` in `tidebot/workflow.py`. They add the `lgtm`, `do-not-merge/hold` and `do-not-merge/wip` labels, and `cancel` as the first word removes them. `/lgtm` works only on PRs. Any other text after `/hold` counts as a reason and still holds.
- `/retitle`, `/lock` (with an optional GitHub lock reason, or `cancel` to unlock), `/milestone` (matches an open milestone by title, `clear` removes it) and `/duplicate #N` (adds a `duplicate` label, closes, and replies "Duplicate of #N" so GitHub links the two). New client methods: `set_title`, `set_milestone`, `find_milestone`, `lock`, `unlock`.
- `/approve` and `/merge`. `/approve` posts an approving review from the App that names who asked for it. `/merge [squash|rebase]` merges only when the PR is open, not a draft, free of conflicts and hold/wip labels, has an approval and no requested changes, and CI is green. CI covers commit statuses and check runs together. A PR with no CI results at all is not merged, since [Commands](README.md#commands) says `/merge` needs CI. The merge pins the head SHA, so a push made after the check makes it fail. When it refuses, the reply lists every reason.

**Next 5%**

- `/ship` (approve and merge in one step), `/vote`, `/kudos`, `/ping`, `/joke` and `/size` from [Community](README.md#community-about-10).
- `/remind 2h ...`: save reminders in `state.json` and post them once they are due.
- `/stats`: count commands run per repo in `state.json` and reply with totals.

**Blockers:** none. Still not run against a live GitHub App; API calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | Pranjal2007v | pranjalgangwar910@gmail.com | `e1a2c9d8284ac658d7dfe929f82e01bec660bcf9` | feat: add /lgtm, /hold and /wip as labels with cancel |
| B | ishitasharma2490 | ishitasharma2490@gmail.com | `4d1924d69dde666a5d16f9972aa64ed7b21c16f1` | feat: add /retitle, /lock, /milestone and /duplicate |
| C | bitflicker64 | himnshuverma10152006@gmail.com | `ec2366b75527f44b08bf62cdbdeb2c183ab36dd6` | feat: add /approve and /merge gated on CI and approval |

## Run 5 (2026-11-01)

**Estimated complete:** 25%

**Added**

- `/ship` in `tidebot/workflow.py`: approves and merges in one step. It runs the same checks as `/merge` except the approval, and refuses before approving when anything else blocks, so a failed `/ship` leaves no approval behind.
- `tidebot/community.py`, a `Community` class that holds the state store and runs the commands from [Community](README.md#community-about-10). `/ping` answers `pong`, `/joke` picks a programming joke, and `/kudos @someone for ...` thanks someone else and keeps a per-repo count.
- `/size` and `tidebot/size.py`: labels a PR `size/XS` to `size/XL` by lines added plus removed (under 10, 30, 100 and 500, then XL) and swaps out an old size label. The buckets are shared so the automatic size label on PR open can use them. `/vote <question>` opens one yes/no vote per issue, `/vote yes` or `/vote no` casts or changes a ballot, `/vote` shows the count and `/vote close` ends it.
- `/remind 2h ...` and `tidebot/reminders.py`: delays such as `30m`, `1h30m` or `2d`, from 1 minute to 30 days. Reminders are saved in `state.json` with their App installation id, and the receiver posts due ones every minute and once at startup. A post that fails with a 5xx or 429 is retried next round; any other failure drops the reminder. `Target` now carries the installation id.
- `/stats`: the receiver counts every allowed command per repo, and `/stats` replies with the total, the five most used commands, kudos given, open votes and waiting reminders.

**Next 5%**

- Automatic behavior when a PR opens, from [Automatic behavior](README.md#automatic-behavior): a welcome comment with the command list, a size label when `size_labels` is on, and a title and description lint when `pr_lint` is on.
- When an issue opens: the `triage` label when `triage_label` is on.
- Assign an issue to whoever comments "I'd like to work on this" when it has no assignee.

**Blockers:** none. Still not run against a live GitHub App; API calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | Pranjal2007v | pranjalgangwar910@gmail.com | `d0701238402c2732c51334fa27a936d5fcafcadd` | feat: add /ship, /ping, /joke and /kudos |
| B | ishitasharma2490 | ishitasharma2490@gmail.com | `90f1e74600e90d6c3067a96793ccac614a744a45` | feat: add /size labels and yes/no /vote per issue |
| C | bitflicker64 | himnshuverma10152006@gmail.com | `49f603f493a6585727adbd5caf6d9409f0efdd88` | feat: add /remind with reminders saved in state.json |
| D | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `5d6cc3e67b43da8e878b5b5ea2651af4f6bb4da6` | feat: add /stats with per-repo command counts |

## Run 6 (2026-11-02)

**Estimated complete:** 30%

**Added**

- `tidebot/events.py` and the receiver now answer `pull_request` and `issues` webhooks, not only comments. When a PR opens, Tidebot posts a welcome comment that lists every command by group and points to `/help` for the ones the author can run. PRs opened by bots get no welcome.
- Size labels on PRs when `size_labels` is on: `size/XS` to `size/XL` on open, using the same buckets as `/size`, and relabeled on each new push (`synchronize`). The line counts and current labels come from the webhook payload, so this costs no extra API reads.
- `tidebot/lint.py`, used when `pr_lint` is on: flags an empty, short (under 10 characters) or long (over 72) title, a WIP title (suggests a draft or `/wip`), titles GitHub fills in such as "Update README.md" or "Patch-1", and a description under 20 characters once template comments are removed. The notes go into the welcome comment and never block a merge.
- When an issue opens, Tidebot adds the `triage` label when `triage_label` is on. A comment such as "I'd like to work on this", "can I take this?" or "assign it to me" on an issue with no assignee assigns it to the commenter and replies. Quoted lines and code blocks don't count. This follows [Automatic behavior](README.md#automatic-behavior), which lets anyone claim an issue, rather than the collaborator tier that `/assign` needs. If GitHub refuses the assignment, Tidebot stays quiet and a maintainer can answer.

**Next 5%**

- Assign reviewers by code area when a PR opens: read a code-area map (a `reviewers` section in `.tide.yml`, or CODEOWNERS), match it against the changed files and request reviews, skipping the author.
- Label new issues by content when `auto_label` is on: keyword rules for `bug`, `enhancement`, `docs` and `question`, using only labels the repo already has.
- Duplicate detection, step one: a TF-IDF similarity score between a new issue and the repo's open issues, with a reply linking close matches. The AI check on borderline matches comes with the AI work.

**Blockers:** none. Still not run against a live GitHub App; API calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | ishitasharma2490 | ishitasharma2490@gmail.com | `fdaf3f36601cc29e7d51704c3b33c04b41c005ea` | feat: welcome new pull requests with the command list |
| B | bitflicker64 | himnshuverma10152006@gmail.com | `c7df0754b3122a5595b63c72bbc20fb4ca30095c` | feat: label PR size on open and relabel it on new pushes |
| C | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `0463b1c763f351768315a280ebdc2d0b950cdbd3` | feat: lint PR titles and descriptions in the welcome comment |
| D | Pranjal2007v | pranjalgangwar910@gmail.com | `e03a3cdd9149117c9e6ecbfbc59aa04419666783` | feat: triage new issues and assign them to whoever asks |

## Run 7 (2026-11-03)

**Estimated complete:** 35%

**Added**

- `tidebot/owners.py`: matches changed files to code owners with CODEOWNERS pattern rules (unanchored names match at any depth, a leading or inner slash anchors to the root, a trailing slash means a directory, `dir/*` covers only the files directly in `dir`, `**` crosses directories, and the last matching rule wins). `.tide.yml` takes a `reviewers` map from pattern to logins or `@org/team` names. When it is set, it replaces CODEOWNERS. Otherwise Tidebot reads `.github/CODEOWNERS`, `CODEOWNERS` or `docs/CODEOWNERS`, the same places GitHub checks.
- Reviewers by code area when a PR opens, from [Automatic behavior](README.md#automatic-behavior). Tidebot lists the PR's files (a renamed file counts under its old path too), asks the owners for a review and leaves out the author and anyone already asked. Teams are requested as teams. Drafts wait until `ready_for_review`, as GitHub does for CODEOWNERS. If GitHub refuses the request, the error is logged and the welcome still posts.
- `tidebot/labeler.py`: when `auto_label` is on, a new issue is labeled bug, enhancement, docs or question by keyword rules. Title words count double. An issue gets bug or enhancement, never both, and a tie gives neither. Only labels the repo already has are used, under their usual names (`bug`, `kind/bug`, `type: bug` and so on). Labels the issue already has, for example from a template, are left alone. The repo's labels are read only when a rule matched.
- `tidebot/duplicates.py`: the TF-IDF half of the duplicate check. A new issue is compared with up to 500 recently updated open issues by cosine similarity, with the title counted twice. Up to three matches scoring 0.5 or more get one reply that links them and points to `/duplicate`. Nothing is closed automatically. Scores from 0.3 to 0.5 are kept for the AI check, which comes with the AI work. A new `duplicate_check` option in `.tide.yml` (default on) turns it off.

**Next 5%**

- The start of [AI commands](README.md#ai-commands-14): a client for any OpenAI-compatible endpoint (`TIDEBOT_AI_URL`, `TIDEBOT_AI_KEY`, `TIDEBOT_AI_MODEL`) with timeouts and a clear reply when no model is configured.
- The AI queue from [Architecture](README.md#architecture): one worker running AI commands in order, so a small server isn't overloaded, with the queue length shown in the reply when a command has to wait.
- First AI commands on top of it: `/ask`, `/summarize` (the issue or PR thread) and `/explain`.
- The AI check on borderline duplicate matches (scores 0.3 to 0.5).

**Blockers:** none. Still not run against a live GitHub App; API calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | bitflicker64 | himnshuverma10152006@gmail.com | `51eb25be287e0ca03a71373d0d9fa5999f83a984` | feat: match changed files to reviewers from CODEOWNERS or .tide.yml |
| B | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `ba7890dc6960e8832693797e8a0195a1421a336a` | feat: request reviews from code owners when a PR opens |
| C | Pranjal2007v | pranjalgangwar910@gmail.com | `9f4c33926f7744e3ac83e02078c91e3bb6ea4201` | feat: label new issues as bug, enhancement, docs or question |
| D | ishitasharma2490 | ishitasharma2490@gmail.com | `029ee81040033a0dea3529c698d20967626784c8` | feat: link likely duplicate issues using TF-IDF similarity |

## Run 8 (2026-11-04)

**Estimated complete:** 40%

**Added**

- `tidebot/ai.py`: a client for any OpenAI-compatible `/chat/completions` endpoint, set up with `TIDEBOT_AI_URL`, `TIDEBOT_AI_MODEL` and an optional `TIDEBOT_AI_KEY` (local servers often have none). It waits up to 60 seconds for an answer. Timeouts, network errors, 429s, other non-200 answers and unreadable or empty replies all become an `AIError` whose message can go straight into a comment and never includes the key. With no model configured, AI commands reply that they are off.
- `tidebot/aiqueue.py`, the AI queue from [Architecture](README.md#architecture): one worker thread runs AI jobs in the order they came in, so a small server makes one model call at a time. The webhook answers GitHub at once and each job posts its own reply. When a command has to wait, Tidebot says how many jobs are ahead of it. A job that fails is logged and the queue moves on.
- `tidebot/aicommands.py`, with the first three [AI commands](README.md#ai-commands-14). `/ask <question>` answers from the issue or PR's title and description (without a question it replies with the usage). `/summarize` reads the whole thread, leaves out bot comments and drops the oldest comments first when the thread is too long. `/explain` describes a PR's change from its diff, or an issue in plain words, and text after it narrows the focus. Context sent to the model is capped at 8000 characters. The other AI commands are still accepted and do nothing yet.
- The AI check on borderline duplicates. When a model is configured, open issues scoring 0.3 to 0.5 against a new issue are sent to the model in pairs on the AI queue, and only the ones it calls the same report are added to the reply, marked "confirmed by the AI check". If nothing is borderline, or there is no model, the reply goes out at once as before. A model error counts as "not the same".

**Next 5%**

- The review pipeline from [How code review works](README.md#how-code-review-works), step one: read the PR thread into a short memo, list the changed files and skip lockfiles and generated code.
- Step two: review each file on its own, four at a time, and collect findings as structured suggestions (path, line range, replacement).
- Step three: check each suggestion against the real lines of the file and drop any that don't apply cleanly.
- `/review` on top of it: up to 12 findings summarized in one comment. Inline suggested changes for `/review-sc` come after.

**Blockers:** none. Still not run against a live GitHub App or a real model endpoint; API and model calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `93717c7eee073f66e1d3ea34b2f2273c6926ad83` | feat: add a client for OpenAI-compatible chat models |
| B | Pranjal2007v | pranjalgangwar910@gmail.com | `d1149416e6978825768ca4abaa197b60f944bae6` | feat: queue AI commands and answer /ask from the issue context |
| C | ishitasharma2490 | ishitasharma2490@gmail.com | `c3754784bcbcda19f4394d816c8aa872345120f2` | feat: add /summarize and /explain for issue and PR threads |
| D | bitflicker64 | himnshuverma10152006@gmail.com | `30331148ac0db260d3167f06ad9a6ff8aa27519a` | feat: check borderline duplicate matches with the AI model |

## Run 9 (2026-11-05)

**Estimated complete:** 45%

**Added**

- `tidebot/review.py`, the pipeline from [How code review works](README.md#how-code-review-works). Step one: `write_memo` turns the PR thread (the same bot-free, newest-first text `/summarize` uses) into a memo of three to five sentences, and `pick_files` drops removed files, lockfiles (`package-lock.json`, `go.sum`, `poetry.lock` and others), generated code (`.min.js`, `_pb2.py`, `vendor/`, `dist/`, or a `Code generated ... DO NOT EDIT` style marker at the top of the file) and files GitHub sends no diff for. At most 30 files are reviewed; the rest are listed as over the limit. New client method `pull_changes` returns the PR's files with their patches.
- Step two: each file goes to the model on its own, four at a time inside the one queued review job, with the memo and its diff numbered by new-file line. The model answers with a JSON array of findings (start and end line, the lines as it read them, the replacement and a short note), which becomes `Suggestion` objects. Fences and text around the array are ignored and malformed items are dropped. A model error marks only that file as not reviewed.
- Step three: `verify` reads each file once at the PR's head commit (`fetch_file` now takes a `ref`) and keeps a suggestion only when its lines sit inside one hunk of the diff, the quoted lines equal the file's real lines (trailing spaces ignored), the replacement changes something and holds no code fence.
- `/review` on a PR runs the three steps and posts one comment: the memo, up to 12 findings each shown as a `diff` block, a count of findings not shown, and a tally of files reviewed, files that failed or were skipped and suggestions dropped. On an issue it says it works on PRs only.

**Next 5%**

- `/review-sc`: post the verified findings as inline suggested changes in one PR review (up to 12, the rest summarized in the review body), per step 4 of [How code review works](README.md#how-code-review-works).
- `/security` and `/perf`: the same per-file pipeline with a focused prompt.
- `/docs` and `/test`: suggest missing docs or tests for the PR's changes.

**Blockers:** none. Still not run against a live GitHub App or a real model endpoint; API and model calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | Pranjal2007v | pranjalgangwar910@gmail.com | `9e71ccd6656800371977fd7b20a15fc81573d48d` | feat: memo the PR thread and pick which changed files to review |
| B | ishitasharma2490 | ishitasharma2490@gmail.com | `f2d97300ae3bf320d8b68249b657c30c8ec8ffd1` | feat: review changed files four at a time into line suggestions |
| C | bitflicker64 | himnshuverma10152006@gmail.com | `cd8a731efabf1098d9a69ebe301ef3e996333b38` | feat: drop review suggestions that do not match the real file lines |
| D | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `e10b7213b1ab356c6945f813bef654dfae9b7049` | feat: add /review with up to 12 verified findings in one comment |

## Run 10 (2026-11-06)

**Estimated complete:** 50%

**Added**

- `/review-sc`, step 4 of [How code review works](README.md#how-code-review-works): it runs the same pipeline as `/review` and posts one PR review at the commit the suggestions were checked against. Up to 12 verified findings go inline as GitHub suggested changes (a multi-line finding covers its whole range, an empty replacement suggests deleting the lines), and the rest are listed one per line in the review body with the memo and the tally. With no findings it posts the usual `/review` comment instead. New client method `post_review` sends a comment-only review; if GitHub refuses it, the reply says so.
- `/security` and `/perf`: the per-file pipeline with a focused prompt (`Focus` in `tidebot/review.py`). `/security` looks only for injection, path traversal, unsafe deserialization, missing auth checks, secrets in code and weak crypto; `/perf` only for repeated work in loops, a call per item where a batch would do, quadratic searches and similar. Findings are verified against the file like `/review` and posted in one comment.
- `/docs`: the same pipeline asking for missing or outdated docstrings and doc comments, written in the file's own style. When the PR changes code but no docs files (README, `*.md`, `docs/` and the like), the reply says the docs may need an update too.
- `/test`: one model call with the PR's code diffs and the names of the test files it already changes. The reply is up to eight test cases, each with the file it belongs in, a name and what it checks. Tests, docs and generated files aren't sent as code, and a PR that changes no code gets a reply without a model call. Text after the command narrows the focus.

**Next 5%**

- The remaining [AI commands](README.md#ai-commands-14): `/changelog` (a release-note line from the PR), `/estimate` (a rough size and effort for an issue), `/checklist` (a review or done checklist for the issue or PR) and `/roast` (a light-hearted take on the PR).
- `/chat`: a back-and-forth with the model in the thread, using the earlier `/chat` turns as context.
- After that, the core bot and AI items in the [Roadmap](README.md#roadmap) can be ticked and the website work starts.

**Blockers:** none. Still not run against a live GitHub App or a real model endpoint; API and model calls are covered by mocked tests.

| Commit | GitHub | Email | SHA | Message |
|---|---|---|---|---|
| A | ishitasharma2490 | ishitasharma2490@gmail.com | `30ddce0c2ee1999c5da5bc08a3715d8634ae4a64` | feat: add /review-sc with inline suggested changes in one PR review |
| B | bitflicker64 | himnshuverma10152006@gmail.com | `52da842bcd2564746af9721ee1ea2411f01f07cc` | feat: add /security and /perf as focused passes of the review pipeline |
| C | Payal-Phougat | 226825128+Payal-Phougat@users.noreply.github.com | `7ee9f5f74c2e9f3a09a6486ba299bd02178a821d` | feat: add /docs to suggest missing doc comments on a PR |
| D | Pranjal2007v | pranjalgangwar910@gmail.com | *(this commit, filled in next run)* | feat: add /test to list the test cases a PR still needs |
