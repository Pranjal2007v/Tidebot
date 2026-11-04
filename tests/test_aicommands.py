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
