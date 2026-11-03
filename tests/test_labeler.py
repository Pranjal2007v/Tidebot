from tidebot.labeler import classify, pick_labels


def test_bug_reports():
    assert classify("App crashes on startup", "Traceback (most recent call last): ...") == ["bug"]
    assert classify("Login doesn't work", "") == ["bug"]


def test_feature_requests():
    assert classify("Add support for GitLab", "It would be nice to have this.") == ["enhancement"]
    assert classify("Feature: dark mode", None) == ["enhancement"]


def test_bug_and_feature_tie_picks_neither():
    assert classify("Feature broken", "") == []


def test_title_counts_double():
    assert classify("Crash when saving", "maybe a new option") == ["bug"]


def test_docs_and_questions():
    assert classify("Typo in the README", "") == ["docs"]
    assert classify("How do I configure the star gate?", "") == ["question"]
    assert classify("Is there a way to skip lint", "") == ["question"]
    assert classify("Docs example fails with an error", "") == ["bug", "docs"]


def test_template_comments_and_empty_text_are_ignored():
    assert classify("Hello", "<!-- Is this a bug? Describe the error -->\nhi") == []
    assert classify(None, None) == []


def test_pick_only_labels_the_repo_has():
    repo = ["Bug", "kind/feature", "triage"]
    assert pick_labels(["bug", "enhancement", "docs"], repo) == ["Bug", "kind/feature"]
    assert pick_labels(["question"], []) == []
