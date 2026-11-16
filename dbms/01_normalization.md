# Normalization of Tidebot's data (1NF → 2NF → 3NF → BCNF)

Tidebot stores its data in three places, and none of them is an SQL database:

| Place | What it holds | Source file |
|-------|---------------|-------------|
| `state.json` (one JSON file, one top-level key per module) | command counts, kudos, votes, reminders, rate-limit history, dashboard metrics | `state.py`, `community.py`, `reminders.py`, `ratelimit.py`, `metrics.py` |
| installations file (JSON, keyed by installation id) | each installation's AI endpoint, model and key | `installations.py` |
| `.tide.yml` in each repo | on/off options and the reviewer rules | `config.py`, `owners.py` |
| memory only (lost on restart) | dashboard sign-in sessions and one-time login states | `signin.py` |

To normalize this we treat each JSON structure as a relation and ask the same questions as for a SQL table: what is the key, what depends on what, and where is a fact stored twice.

**Assumptions**
1. A GitHub repo name (`owner/name`) and a GitHub login are natural identifiers, so they are stored as text and there is no `users` table. Logins are compared in lowercase, as the code does.
2. One repo belongs to one App installation at a time.
3. An issue or PR number is unique only inside its repo.
4. Reminders have no id in the code. A surrogate `reminder_id` is added in the relational version.

---

## 0. Unnormalized data (what the code stores today)

```json
{
  "stats":   { "owner/repo": { "review": 4, "ask": 7 } },
  "kudos":   { "owner/repo": { "alice": 2 } },
  "votes":   { "owner/repo#12": { "question": "Drop Python 3.8?", "opened_by": "bob",
                                  "ballots": { "alice": "yes", "carol": "no" } } },
  "reminders": [ { "repo": "owner/repo", "number": 12, "installation": 12345678,
                   "author": "bob", "due": 1795000000.0, "text": "check CI" } ],
  "rate_limits": { "users": { "owner/repo:bob": [1795000001.2, 1795000050.7] },
                   "repos": { "owner/repo": [1795000001.2, 1795000050.7, 1795000120.4] } },
  "metrics": { "owner/repo": { "queue_waits": [0.0, 2.3, 1.1],
                               "reviews": { "review": 3, "security": 1 },
                               "duplicates": 2 } }
}
```

Installations file:
```json
{ "12345678": { "ai_url": "https://api.example.com/v1", "ai_model": "small-model", "ai_key": "..." } }
```

`.tide.yml`:
```yaml
auto_label: true
size_labels: true
star_gate: false
triage_label: true
pr_lint: true
duplicate_check: true
reviewers:
  docs/: [alice]
  "*.py": [bob, "@org/backend"]
```

---

## 1. First Normal Form (1NF)

**Rule:** every cell holds one atomic value, there are no repeating groups or lists inside a cell, and every row is identified by a key.

**1NF violations found**

| Structure | Violation | Fix |
|-----------|-----------|-----|
| `votes` key `"owner/repo#12"` | Two values (repo and issue number) packed into one string | Two columns: `repo`, `number` |
| `votes[...].ballots` | A map of voter → choice inside one record (repeating group) | One row per ballot |
| `rate_limits.users` key `"owner/repo:bob"` | Repo and login packed into one string | Two columns: `repo`, `user_login` |
| `rate_limits` timestamp lists | A list of times inside one cell | One row per command run |
| `metrics.queue_waits` | A list of numbers inside one cell | One row per measured wait |
| `stats`, `kudos`, `metrics.reviews` | Command names and logins are used as **JSON keys**, so data sits in the structure instead of in columns | Rows of `(repo, command, count)` and `(repo, login, count)` |
| `.tide.yml` `reviewers` | A list of owners inside one rule | One row per owner, plus a position column, because the last matching rule wins |

**Result (1NF relations, with primary keys)**

```
stats_1nf        (repo, command, run_count)                                   PK (repo, command)
kudos_1nf        (repo, login, kudos_count)                                   PK (repo, login)
vote_ballots_1nf (repo, number, question, opened_by, voter, choice)           PK (repo, number, voter)
reminders_1nf    (reminder_id, repo, number, installation, author, due_at, text)   PK (reminder_id)
command_hits_1nf (repo, user_login, hit_at, repo_bucket_hit_at)               PK (repo, user_login, hit_at)
queue_waits_1nf  (repo, wait_seq, wait_seconds)                               PK (repo, wait_seq)
review_counts_1nf(repo, command, review_count, duplicates_caught)             PK (repo, command)
reviewer_rules_1nf(repo, position, pattern, owner)                            PK (repo, position, owner)
installations    (installation_id, ai_url, ai_model, ai_key)                  PK (installation_id)
repo_config      (repo, auto_label, size_labels, star_gate, triage_label, pr_lint, duplicate_check)   PK (repo)
```

These are in 1NF but still have redundancy. The next steps remove it.

---

## 2. Second Normal Form (2NF)

**Rule:** 1NF, and no non-key column depends on only **part** of a composite key.

Partial dependencies found:

| 1NF relation | Composite key | Partial dependency | Why it is a problem |
|--------------|---------------|--------------------|---------------------|
| `vote_ballots_1nf` | (repo, number, voter) | (repo, number) → question, opened_by | The question is repeated on every ballot. Changing it needs many updates, and a vote with no ballots yet has no place to store its question |
| `review_counts_1nf` | (repo, command) | repo → duplicates_caught | The duplicates counter is repeated for every review command of the repo |
| `reviewer_rules_1nf` | (repo, position, owner) | (repo, position) → pattern | The pattern is repeated for every owner of the rule, and a rule with no owner (which the code allows: it leaves a file unowned) cannot be stored at all |
| `command_hits_1nf` | (repo, user_login, hit_at) | the `repo_bucket_hit_at` column is a copy of the same event | See section 3 |

**Fix: split each relation so every non-key column depends on the whole key**

```
votes             (repo, number, question, opened_by)               PK (repo, number)
vote_ballots      (repo, number, voter, choice)                     PK (repo, number, voter)
                                                                    FK (repo, number) → votes

review_counts     (repo, command, review_count)                     PK (repo, command)
repos             (repo, installation_id, duplicates_caught)        PK (repo)   [installation_id: see section 3]

reviewer_rules       (repo, position, pattern)                      PK (repo, position)
reviewer_rule_owners (repo, position, owner)                        PK (repo, position, owner)
                                                                    FK (repo, position) → reviewer_rules
```

---

## 3. Third Normal Form (3NF)

**Rule:** 2NF, and no non-key column depends on another non-key column (no transitive dependency).

**Transitive dependency found: `reminders`**

The code saves the App `installation` id inside every reminder (so the bot can fetch the right token later). But the installation is decided by the repo:

```
reminder_id → repo → installation_id        (transitive)
```

So the same `(repo, installation_id)` pair is repeated in every reminder of that repo, and it can become inconsistent. Fix: keep `installation_id` once, in `repos`, and remove it from `reminders`.

```
repos      (repo, installation_id, duplicates_caught)      PK (repo)      FK installation_id → installations
reminders  (reminder_id, repo, number, author, due_at, text)   PK (reminder_id)   FK repo → repos
```

**Redundant data found: the rate limiter's two buckets**

`ratelimit.py` writes every allowed command twice: once into `users["repo:user"]` and once into `repos["repo"]`. The repo bucket is always the union of the user buckets of that repo (after the same one-hour pruning). A per-repo count is therefore **derivable** from one table of hits:

```
command_hits (repo, user_login, hit_at)                       PK (repo, user_login, hit_at)
-- per-user limit: count rows for (repo, user_login) in the last hour
-- per-repo limit: count rows for (repo) in the last hour
```

The code keeps both lists as a speed shortcut on a tiny server. In the relational model only one copy is stored.

**Derived values that are not stored as columns**

| Value | Computed from |
|-------|---------------|
| total commands run (`/stats`, dashboard) | `SUM(run_count)` over `command_stats` |
| reviews total | `SUM(review_count)` over `review_counts` |
| queue jobs, median wait, max wait | the rows of `queue_waits` |
| kudos given in a repo | `SUM(kudos_count)` over `kudos` |
| vote tally (yes / no) | `COUNT(*)` of `vote_ballots` grouped by `choice` |
| open votes, reminders waiting | `COUNT(*)` of `votes` and `reminders` |

**Memory-only data (dashboard sign-in), also in 3NF**

```
web_sessions        (session_id, login, token, expires_at)     PK (session_id)
session_push_access (session_id, repo, can_push)               PK (session_id, repo)   FK session_id → web_sessions
oauth_states        (state, return_to, expires_at)             PK (state)
```
`push` in the code is a map repo → true/false inside the session (a repeating group), so it becomes its own table.

---

## 4. Boyce–Codd Normal Form (BCNF)

**Rule:** for every functional dependency `X → Y`, `X` must be a superkey.

Every table below is in **BCNF**. The only determinants are the primary keys (or other candidate keys).

| Table | Primary key | Functional dependencies | BCNF? |
|-------|-------------|-------------------------|:-----:|
| installations | installation_id | installation_id → ai_url, ai_model, ai_key | yes |
| repos | repo | repo → installation_id, duplicates_caught | yes |
| repo_config | repo | repo → auto_label, size_labels, star_gate, triage_label, pr_lint, duplicate_check | yes |
| reviewer_rules | (repo, position) | (repo, position) → pattern | yes |
| reviewer_rule_owners | (repo, position, owner) | none (all key) | yes |
| command_stats | (repo, command) | (repo, command) → run_count | yes |
| kudos | (repo, login) | (repo, login) → kudos_count | yes |
| votes | (repo, number) | (repo, number) → question, opened_by | yes |
| vote_ballots | (repo, number, voter) | (repo, number, voter) → choice | yes |
| reminders | reminder_id | reminder_id → repo, number, author, due_at, text | yes |
| command_hits | (repo, user_login, hit_at) | none (all key) | yes |
| queue_waits | (repo, wait_seq) | (repo, wait_seq) → wait_seconds | yes |
| review_counts | (repo, command) | (repo, command) → review_count | yes |
| web_sessions | session_id | session_id → login, token, expires_at | yes |
| session_push_access | (session_id, repo) | (session_id, repo) → can_push | yes |
| oauth_states | state | state → return_to, expires_at | yes |

Notes on the choices:
- `web_sessions`: there is **no** dependency `login → token`. A user gets a new token on every sign-in, so one login can have many sessions. This is why the session id, not the login, is the key.
- `reminders`: there is no natural key. Two identical reminders (same repo, issue, author, time and text) are legal, so a surrogate `reminder_id` is used.
- `reviewer_rules.position` is needed because order matters: in CODEOWNERS syntax the last matching rule wins.
- Counters (`run_count`, `kudos_count`, `review_count`, `duplicates_caught`) are stored **on purpose**. The bot keeps no log of every command, so these numbers are base facts and not derived from anything. This is a design choice for a small server with no database, not a normal-form violation.
- `queue_waits` keeps only the latest 200 rows per repo (`MAX_WAITS` in `metrics.py`) so the state file stays small. `wait_seq` keeps their order.

---

## 5. Final relational schema (summary)

```
installations        (installation_id PK, ai_url, ai_model, ai_key NULL)
repos                (repo PK, installation_id FK NULL, duplicates_caught)
repo_config          (repo PK/FK, auto_label, size_labels, star_gate, triage_label, pr_lint, duplicate_check)
reviewer_rules       (repo FK, position, pattern)                    PK (repo, position)
reviewer_rule_owners (repo, position, owner)                         PK (repo, position, owner)  FK (repo, position)
command_stats        (repo FK, command, run_count)                   PK (repo, command)
kudos                (repo FK, login, kudos_count)                   PK (repo, login)
votes                (repo FK, number, question, opened_by)          PK (repo, number)
vote_ballots         (repo, number, voter, choice)                   PK (repo, number, voter)    FK (repo, number)
reminders            (reminder_id PK, repo FK, number, author, due_at, text)
command_hits         (repo FK, user_login, hit_at)                   PK (repo, user_login, hit_at)
queue_waits          (repo FK, wait_seq, wait_seconds)               PK (repo, wait_seq)
review_counts        (repo FK, command, review_count)                PK (repo, command)
web_sessions         (session_id PK, login, token, expires_at)       [memory only]
session_push_access  (session_id FK, repo, can_push)                 PK (session_id, repo)   [memory only]
oauth_states         (state PK, return_to, expires_at)               [memory only]
```

## 6. Relationships

| Relationship | Cardinality |
|--------------|-------------|
| installations – repos | 1 : N |
| repos – repo_config | 1 : 1 |
| repos – reviewer_rules | 1 : N |
| reviewer_rules – reviewer_rule_owners | 1 : N |
| repos – command_stats / kudos / review_counts / queue_waits / command_hits / reminders | 1 : N each |
| repos – votes | 1 : N (at most one open vote per issue) |
| votes – vote_ballots | 1 : N (one ballot per voter, a voter can change their answer) |
| web_sessions – session_push_access | 1 : N |

## 7. Summary of what changed at each step

| Step | Problem removed | Example |
|------|-----------------|---------|
| 1NF | Packed keys, nested maps and lists | `"owner/repo#12"` → `repo`, `number`; `ballots` map → rows |
| 2NF | Partial dependencies | `question` moved out of the ballots table into `votes` |
| 3NF | Transitive dependency and duplicated data | `installation` moved from `reminders` to `repos`; rate-limit repo bucket removed |
| BCNF | None left | every determinant is a key |

**Limitation:** this is a relational model of the JSON file, written from reading the code. The bot itself still uses `state.json`. Moving it to PostgreSQL would follow the schema in section 5.