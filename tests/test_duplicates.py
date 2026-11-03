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
