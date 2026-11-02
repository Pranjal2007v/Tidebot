from tidebot.lint import lint_comment, lint_description, lint_pull_request, lint_title


def test_good_title_passes():
    assert lint_title("Retry webhook deliveries on 5xx") == []


def test_title_problems():
    assert "Add a title" in lint_title("  ")[0]
    assert "/wip" in lint_title("WIP: retry deliveries")[0]
    assert "/wip" in lint_title("[WIP] retry deliveries")[0]
    assert "GitHub suggested" in lint_title("Update README.md")[0]
    assert "GitHub suggested" in lint_title("Patch-1")[0]
    assert "short" in lint_title("Fix bug")[0]
    assert "under 72" in lint_title("x" * 80)[0]


def test_title_starting_with_wipe_is_not_wip():
    assert lint_title("Wipe the cache when config changes") == []


def test_description_template_comments_do_not_count():
    assert lint_description("<!-- Describe your change here -->\n\n") != []
    assert lint_description(None) != []
    assert lint_description("Retries twice, then posts the error to the thread.") == []


def test_lint_comment():
    assert lint_comment([]) is None
    findings = lint_pull_request({"title": "Fix", "body": ""})
    assert len(findings) == 2
    assert lint_comment(findings).startswith("A few things that would help reviewers:\n\n- ")
