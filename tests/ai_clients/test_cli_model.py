"""``--model`` on the commands: the SLM is the default and keeps its behaviour (FR-028, FR-029)."""

import pytest

from ai_clients import __main__ as cli


def parse(*argv):
    return cli.build_parser().parse_args(list(argv))


@pytest.mark.parametrize(
    "argv",
    [
        ["generate"],
        ["close", "--problem", "1_A", "--scenario", "hybrid", "--reason", "x"],
        ["change-template", "--template", "solution", "--reason", "x"],
        ["report"],
        ["package"],
        ["verify"],
        ["execute"],
    ],
)
def test_every_command_takes_model_and_defaults_to_the_slm(argv):
    assert parse(*argv).model == "slm"
    assert parse(*argv, "--model", "gemini").model == "gemini"


def test_an_unknown_model_is_a_usage_error():
    assert cli.main(["report", "--model", "llama"]) == cli.EXIT_USAGE


@pytest.mark.parametrize("model", ["gpt", "gemini"])
def test_execute_refuses_a_commercial_model(model, capsys):
    assert cli.main(["execute", "--model", model]) == cli.EXIT_USAGE
    assert "the commercial models run nothing: there is no execute step" in capsys.readouterr().err


def test_confirm_spend_is_only_for_the_commercial_models(capsys):
    assert cli.main(["generate", "--confirm-spend", "3"]) == cli.EXIT_USAGE
    assert "--confirm-spend is only for" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-1", "lots"])
def test_confirm_spend_must_be_a_positive_amount(value):
    assert cli.main(["generate", "--model", "gpt", "--confirm-spend", value]) == cli.EXIT_USAGE


def test_the_templates_of_the_two_modules_never_mix(capsys):
    assert cli.main(["change-template", "--template", "llm", "--reason", "x"]) == cli.EXIT_USAGE
    assert (
        cli.main(["change-template", "--model", "gpt", "--template", "solution", "--reason", "x"])
        == cli.EXIT_USAGE
    )


def test_the_new_exit_codes_and_their_precedence():
    assert (cli.EXIT_SPEND_CAP, cli.EXIT_NO_REASONING) == (5, 6)
    combine = cli.combine_codes
    assert combine({130, 3, 6, 1, 5, 4}) == 130
    assert combine({3, 6, 1, 5, 4}) == 3
    assert combine({6, 1, 5, 4}) == 6
    assert combine({1, 5, 4}) == 1
    assert combine({5, 4}) == 5
    assert combine({4, 0}) == 4
    assert combine({0}) == 0
