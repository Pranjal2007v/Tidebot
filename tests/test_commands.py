from tidebot.commands import ALL_COMMANDS, Command, parse_commands


def test_triggered_command_with_args():
    assert parse_commands(":tide /ask where is auth handled?") == [
        Command("ask", "where is auth handled?")
    ]


def test_command_without_args_and_case_insensitive():
    assert parse_commands(":TIDE /Hold") == [Command("hold")]


def test_hyphenated_command():
    assert parse_commands(":tide /review-sc") == [Command("review-sc")]


def test_multiple_commands_in_order():
    body = "Thanks!\n:tide /label bug\nmore text\n  :tide /assign @me  \n"
    assert parse_commands(body) == [Command("label", "bug"), Command("assign", "@me")]


def test_bare_lgtm_on_its_own_line():
    assert parse_commands("Looks good.\n/lgtm\n") == [Command("lgtm", bare=True)]


def test_bare_non_lgtm_is_ignored():
    assert parse_commands("/merge\n/hold") == []


def test_trigger_mid_line_is_ignored():
    assert parse_commands("you can type :tide /help to see commands") == []


def test_mention_style_is_not_a_trigger():
    assert parse_commands("@tide /help") == []


def test_code_fences_and_quotes_are_ignored():
    body = "```\n:tide /merge\n```\n> :tide /close\n> /lgtm\n~~~\n/lgtm\n~~~\n:tide /ping"
    assert parse_commands(body) == [Command("ping")]


def test_empty_body():
    assert parse_commands("") == []
    assert parse_commands(None) == []


def test_known_flag():
    assert Command("merge").known
    assert not Command("teleport").known
    assert parse_commands(":tide /teleport") == [Command("teleport")]


def test_every_group_is_in_all_commands():
    assert {"ask", "merge", "help"} <= ALL_COMMANDS
