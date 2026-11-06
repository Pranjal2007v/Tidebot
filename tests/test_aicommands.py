from tidebot.ai import AIError
from tidebot.aicommands import clip, make_job, usage_error
from tidebot.commands import Command
from tidebot.github import GitHubError
from tidebot.workflow import Target

TARGET = Target("o/r", 4, False, "alice", 99)


class FakeGitHub:
    def __init__(self, issue=None, comments=(), diff=""):
        self._issue = issue or {"title": "Login fails", "body": "Token is rejected."}
        self._comments = list(comments)
        self._diff = diff
        self.calls = []

    def issue(self, repo, number):
        self.calls.append(("issue", repo, number))
        return self._issue

    def issue_comments(self, repo, number):
        self.calls.append(("issue_comments", repo, number))
        return self._comments

    def pull_diff(self, repo, number):
        self.calls.append(("pull_diff", repo, number))
        return self._diff

    def post_comment(self, repo, number, body):
        self.calls.append(("post_comment", repo, number, body))


class FakeAI:
    def __init__(self, answer="An answer.", error=None):
        self.answer = answer
        self.error = error
        self.prompts = []

    def ask(self, system, user, **kwargs):
        self.prompts.append((system, user))
        if self.error:
            raise self.error
        return self.answer


def run(gh, ai, text, target=TARGET):
    name, _, args = text.partition(" ")
    make_job(gh, target, Command(name, args))(ai)
    return gh.calls[-1]


def test_ask_sends_the_question_with_the_issue_as_context():
    gh, ai = FakeGitHub(), FakeAI("Auth is in `app.py`.")
    call = run(gh, ai, "ask where is auth handled?")
    assert call == ("post_comment", "o/r", 4, "`/ask` for @alice:\n\nAuth is in `app.py`.")
    system, user = ai.prompts[0]
    assert "o/r" in system
    assert user.startswith("Issue #4: Login fails\n\nToken is rejected.")
    assert user.endswith("Question: where is auth handled?")


def test_ask_needs_a_question():
    assert usage_error(Command("ask")) == "Usage: `:tide /ask where is auth handled?`"
    assert usage_error(Command("ask", "why?")) is None
    assert usage_error(Command("ping")) is None


def test_model_and_github_errors_become_replies():
    gh = FakeGitHub()
    call = run(gh, FakeAI(error=AIError("the model took too long to answer")), "ask why?")
    assert call[3] == "`/ask` failed: the model took too long to answer"

    class Broken(FakeGitHub):
        def issue(self, repo, number):
            raise GitHubError(404, "gone")

    gh = Broken()
    assert run(gh, FakeAI(), "ask why?")[3] == "`/ask` failed: GitHub answered 404"


def test_clip():
    assert clip("  short ") == "short"
    assert clip(None) == ""
    assert clip("abcdef", 3) == "abc\n[...cut for length]"


def comment(login, body):
    return {"user": {"login": login}, "body": body}


def test_summarize_sends_the_thread_without_bot_comments():
    gh = FakeGitHub(issue={"title": "Login fails", "body": "Token is rejected.",
                           "user": {"login": "carol"}},
                    comments=[comment("dave", "Same here on 1.2."),
                              comment("tidebot[bot]", "This issue looks similar to: #2"),
                              comment("erin", "Fixed by rotating the key?")])
    ai = FakeAI("- Login fails\n- Still open")
    assert run(gh, ai, "summarize")[3] == "`/summarize` for @alice:\n\n- Login fails\n- Still open"
    system, user = ai.prompts[0]
    assert "Summarize" in system
    assert user == ("Issue #4 by @carol: Login fails\n\nToken is rejected.\n\n"
                    "@dave: Same here on 1.2.\n\n@erin: Fixed by rotating the key?")


def test_long_threads_keep_the_latest_comments():
    from tidebot.aicommands import thread_text

    comments = [comment("u", f"comment {i} " + "x" * 50) for i in range(10)]
    text = thread_text({"title": "t", "body": "b"}, comments, True, 9, limit=200)
    assert text.startswith("Pull request #9 by @someone: t\n\nb")
    assert "comment 9" in text and "comment 0" not in text
    assert "earlier comments left out]" in text
    assert len(text) <= 200


def test_explain_a_pr_sends_its_diff():
    gh = FakeGitHub(diff="--- a/app.py\n+++ b/app.py\n+retry()")
    ai = FakeAI("It adds a retry.")
    target = Target("o/r", 4, True, "alice")
    assert run(gh, ai, "explain the retry", target)[3] == "`/explain` for @alice:\n\nIt adds a retry."
    system, user = ai.prompts[0]
    assert "pull request" in system
    assert user.startswith("Pull request #4: Login fails")
    assert "Diff:\n--- a/app.py" in user and user.endswith("Focus on: the retry")


def test_explain_a_pr_whose_diff_is_too_large():
    ai = FakeAI()
    run(FakeGitHub(diff=""), ai, "explain", Target("o/r", 4, True, "alice"))
    assert "(The diff is too large to include.)" in ai.prompts[0][1]


def test_explain_an_issue_needs_no_diff():
    gh, ai = FakeGitHub(), FakeAI()
    run(gh, ai, "explain")
    assert ("pull_diff", "o/r", 4) not in gh.calls
    assert "plain words" in ai.prompts[0][0]
    assert usage_error(Command("explain")) is None


class ReviewGitHub(FakeGitHub):
    def __init__(self, changes, files):
        super().__init__({"title": "Bump x", "body": "Fixes the counter.", "user": {"login": "alice"}})
        self.changes = changes
        self.files = files

    def pull(self, repo, number):
        return {"head": {"sha": "abc"}}

    def pull_changes(self, repo, number):
        return self.changes

    def fetch_file(self, repo, path, ref=None):
        self.calls.append(("fetch_file", path, ref))
        return self.files.get(path)

    def post_review(self, repo, number, sha, body, comments):
        self.calls.append(("post_review", repo, number, sha, body, comments))


class ReviewAI:
    def __init__(self, findings):
        self.findings = findings
        self.prompts = []

    def ask(self, system, user, **kwargs):
        self.prompts.append(user)
        if "memo" in system:
            return "It bumps x."
        return self.findings


PR = Target("o/r", 5, True, "alice", 99)


def test_review_posts_verified_findings_on_a_pr():
    changes = [{"filename": "a.py", "status": "modified",
                "patch": "@@ -1,2 +1,2 @@\n import os\n-x = 1\n+x = 2"},
               {"filename": "yarn.lock", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"}]
    gh = ReviewGitHub(changes, {"a.py": "import os\nx = 2\n"})
    ai = ReviewAI('[{"start": 2, "original": "x = 2", "replacement": "x = 3", "note": "Too low."},'
                  ' {"start": 2, "original": "y = 2", "replacement": "y = 3"}]')
    body = run(gh, ai, "review", PR)[3]
    assert body.startswith("`/review` for @alice:\n\n**What this PR does:** It bumps x.")
    assert "1. `a.py` line 2: Too low.\n\n````diff\n-x = 2\n+x = 3\n````" in body
    assert body.endswith("Reviewed 1 file. Skipped: `yarn.lock` (lockfile). "
                         "Dropped 1 suggestion that didn't match the file.")
    assert ("fetch_file", "a.py", "abc") in gh.calls
    assert ai.prompts[0].startswith("Pull request #5 by @alice: Bump x")
    assert "It bumps x." in ai.prompts[1] and "File: a.py" in ai.prompts[1]


def test_review_needs_a_pr_and_something_to_review():
    gh = ReviewGitHub([], {})
    assert run(gh, ReviewAI("[]"), "review")[3].endswith("`/review` works on pull requests only.")
    gh = ReviewGitHub([{"filename": "go.sum", "patch": "@@ -1 +1 @@\n-a\n+b"}], {})
    ai = ReviewAI("[]")
    assert run(gh, ai, "review", PR)[3].endswith("Nothing to review: every changed file is a "
                                                 "lockfile, generated, removed or binary.")
    assert ai.prompts == []


A_PY = [{"filename": "a.py", "status": "modified",
         "patch": "@@ -1,2 +1,2 @@\n import os\n-x = 1\n+x = 2"}]


def test_review_sc_posts_inline_suggestions_in_one_review():
    gh = ReviewGitHub(A_PY, {"a.py": "import os\nx = 2\n"})
    ai = ReviewAI('[{"start": 2, "original": "x = 2", "replacement": "x = 3", "note": "Too low."}]')
    call = run(gh, ai, "review-sc", PR)
    assert call[:4] == ("post_review", "o/r", 5, "abc")
    assert call[4] == ("`/review-sc` for @alice:\n\n**What this PR does:** It bumps x."
                       "\n\nReviewed 1 file.")
    assert call[5] == [{"path": "a.py", "line": 2, "side": "RIGHT",
                        "body": "Too low.\n\n```suggestion\nx = 3\n```"}]
    assert not any(c[0] == "post_comment" for c in gh.calls)


def test_review_sc_puts_findings_past_twelve_in_the_body():
    lines = [f"x{n} = {n}" for n in range(1, 16)]
    patch = "@@ -0,0 +1,15 @@\n" + "\n".join("+" + line for line in lines)
    gh = ReviewGitHub([{"filename": "a.py", "status": "added", "patch": patch}],
                      {"a.py": "\n".join(lines)})
    found = ", ".join(f'{{"start": {n}, "original": "x{n} = {n}", "replacement": "x{n} = 0"}}'
                      for n in range(1, 16))
    call = run(gh, ReviewAI(f"[{found}]"), "review-sc", PR)
    assert len(call[5]) == 12
    assert "**3 more findings** past the 12 shown inline:\n- `a.py` line 13" in call[4]


def test_review_sc_without_findings_comments_instead():
    gh = ReviewGitHub(A_PY, {"a.py": "import os\nx = 2\n"})
    call = run(gh, ReviewAI("[]"), "review-sc", PR)
    assert call[0] == "post_comment"
    assert "No problems found in the reviewed files." in call[3]
    assert run(gh, ReviewAI("[]"), "review-sc")[3].endswith(
        "`/review-sc` works on pull requests only.")


def test_review_sc_reports_a_refused_review():
    class Refusing(ReviewGitHub):
        def post_review(self, *args):
            raise GitHubError(422, "line must be part of the diff")

    gh = Refusing(A_PY, {"a.py": "import os\nx = 2\n"})
    ai = ReviewAI('[{"start": 2, "original": "x = 2", "replacement": "x = 3"}]')
    assert run(gh, ai, "review-sc", PR)[3] == "`/review-sc` failed: GitHub answered 422"


def test_security_and_perf_review_with_their_own_focus():
    class Recording(ReviewAI):
        def ask(self, system, user, **kwargs):
            self.systems = getattr(self, "systems", []) + [system]
            return super().ask(system, user, **kwargs)

    for name, label in (("security", "security problems"), ("perf", "performance problems")):
        gh = ReviewGitHub(A_PY, {"a.py": "import os\nx = 2\n"})
        ai = Recording("[]")
        body = run(gh, ai, name, PR)[3]
        assert body.startswith(f"`/{name}` for @alice:\n\n**What this PR does:** It bumps x.")
        assert f"No {label} found in the reviewed files." in body
        assert label in ai.systems[1]
        assert run(gh, ai, name)[3].endswith(f"`/{name}` works on pull requests only.")


def test_security_findings_are_verified_like_review():
    gh = ReviewGitHub(A_PY, {"a.py": "import os\nx = 2\n"})
    ai = ReviewAI('[{"start": 2, "original": "x = 2", "replacement": "x = int(os.environ[\'X\'])",'
                  ' "note": "Hard-coded."}, {"start": 9, "original": "y", "replacement": "z"}]')
    body = run(gh, ai, "security", PR)[3]
    assert "1. `a.py` line 2: Hard-coded." in body
    assert body.endswith("Dropped 1 suggestion that didn't match the file.")


def test_docs_suggests_docstrings_and_notes_untouched_docs():
    patch = "@@ -0,0 +1,2 @@\n+def retry(n):\n+    return n"
    gh = ReviewGitHub([{"filename": "a.py", "status": "added", "patch": patch}],
                      {"a.py": "def retry(n):\n    return n\n"})
    ai = ReviewAI('[{"start": 1, "original": "def retry(n):", "replacement": '
                  '"def retry(n):\\n    \\"\\"\\"Retry n times.\\"\\"\\"", "note": "No docstring."}]')
    body = run(gh, ai, "docs", PR)[3]
    assert "1. `a.py` line 1: No docstring." in body
    assert '+    """Retry n times."""' in body
    assert body.endswith("If it changes how something is used, the docs may need an update too.")


def test_docs_skips_the_note_when_docs_changed():
    changes = A_PY + [{"filename": "README.md", "status": "modified",
                       "patch": "@@ -1 +1 @@\n-old\n+new"}]
    gh = ReviewGitHub(changes, {"a.py": "import os\nx = 2\n"})
    body = run(gh, ReviewAI("[]"), "docs", PR)[3]
    assert body.endswith("Reviewed 2 files.")
    assert "No missing docs found in the reviewed files." in body
    assert run(gh, ReviewAI("[]"), "docs")[3].endswith("`/docs` works on pull requests only.")
