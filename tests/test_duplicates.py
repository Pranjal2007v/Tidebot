from tidebot.duplicates import duplicates_comment, find_duplicates, tokens

OPEN = [
    {"number": 1, "title": "Webhook signature check fails behind Cloudflare tunnel",
     "body": "Every delivery gets a 401 bad signature when running behind the tunnel."},
    {"number": 2, "title": "Add dark mode to the dashboard", "body": "The dashboard is too bright."},
    {"number": 3, "title": "Reminders are posted twice after restart",
     "body": "A /remind fires again when the bot restarts."},
    {"number": 4, "title": "Typo in README", "body": "Configuration is spelled wrong."},
]


def test_tokens_drop_stopwords_and_template_comments():
    assert tokens("The bot is down", "<!-- describe it -->ok") == ["bot", "down", "bot", "down", "ok"]


def test_close_match_is_found():
    new = {"number": 9, "title": "Bad signature 401 on every webhook behind cloudflare tunnel",
           "body": "Signature check fails."}
    matches = find_duplicates(new, OPEN)
    assert [m.number for m in matches] == [1]
    assert matches[0].score >= 0.5


def test_unrelated_issue_has_no_matches():
    new = {"number": 9, "title": "Support GitLab merge requests", "body": "Would be useful."}
    assert find_duplicates(new, OPEN) == []


def test_new_issue_and_pull_requests_are_not_candidates():
    new = {"number": 3, "title": "Reminders are posted twice after restart", "body": ""}
    pr = {"number": 5, "title": "Reminders are posted twice after restart",
          "pull_request": {}}
    assert find_duplicates(new, OPEN + [pr]) == []


def test_empty_issue_matches_nothing():
    assert find_duplicates({"number": 9, "title": "", "body": None}, OPEN) == []


def test_best_matches_first_and_capped():
    same = [{"number": n, "title": "Crash on startup", "body": ""} for n in range(10, 15)]
    matches = find_duplicates({"number": 9, "title": "Crash on startup"}, same)
    assert [m.number for m in matches] == [10, 11, 12]


def test_comment_lists_matches():
    new = {"number": 9, "title": "Reminder posted twice after a restart", "body": ""}
    text = duplicates_comment(find_duplicates(new, OPEN))
    assert text.startswith("This issue looks similar to:")
    assert "- #3 Reminders are posted twice after restart (" in text
    assert "/duplicate #N" in text
    assert duplicates_comment([]) is None


from tidebot.ai import AIError
from tidebot.duplicates import Match, confirm_borderline, same_report, split_matches

NEW = {"number": 9, "title": "Webhook crashes on startup",
       "body": "The receiver crashes when the state file is missing."}
MIXED = [
    {"number": 1, "title": "Webhook crashes on startup",
     "body": "Crash when state file is missing on first run."},
    {"number": 2, "title": "Receiver fails when the state file is missing",
     "body": "Starting the receiver errors out."},
    {"number": 3, "title": "Add dark mode to dashboard", "body": "Please add a dark theme."},
]


class Model:
    def __init__(self, answers=None, error=None):
        self.answers = answers or {}
        self.error = error
        self.prompts = []

    def ask(self, system, user, **kwargs):
        self.prompts.append((system, user, kwargs))
        if self.error:
            raise self.error
        for title, answer in self.answers.items():
            if title in user.split("Issue B: ", 1)[1]:
                return answer
        return "no"


def test_split_matches_separates_clear_and_borderline():
    strong, borderline = split_matches(NEW, MIXED)
    assert [m.number for m in strong] == [1]
    assert [m.number for m in borderline] == [2]
    assert 0.3 <= borderline[0].score < 0.5


def test_same_report_asks_for_yes_or_no():
    model = Model({"Receiver fails": "Yes."})
    assert same_report(model, NEW, MIXED[1]) is True
    system, user, kwargs = model.prompts[0]
    assert "yes or no" in system
    assert "Issue A: Webhook crashes on startup" in user
    assert kwargs == {"max_tokens": 5, "temperature": 0}
    assert same_report(Model(), NEW, MIXED[2]) is False


def test_same_report_counts_model_errors_as_no(capsys):
    assert same_report(Model(error=AIError("the model took too long to answer")),
                       NEW, MIXED[1]) is False
    assert "too long" in capsys.readouterr().out


def test_confirm_borderline_adds_only_what_the_model_confirms():
    strong = [Match(1, "Webhook crashes on startup", 0.83)]
    borderline = [Match(2, "Receiver fails when the state file is missing", 0.31),
                  Match(3, "Add dark mode to dashboard", 0.30)]
    matches = confirm_borderline(Model({"Receiver fails": "yes"}), NEW, MIXED,
                                 strong, borderline)
    assert [(m.number, m.checked) for m in matches] == [(1, False), (2, True)]
    text = duplicates_comment(matches)
    assert "- #1 Webhook crashes on startup (83% similar)" in text
    assert "- #2 Receiver fails when the state file is missing (31% similar, " \
           "confirmed by the AI check)" in text
