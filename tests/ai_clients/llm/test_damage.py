"""A damaged combination is skipped and listed by every command; nothing is repaired."""

from ai_clients import __main__ as cli
from ai_clients.llm import store


def damage(repo):
    folder = store.combination_dir(repo, "gpt", "2_B", "hybrid")
    (folder / "attempt_1.json").write_text("{broken")


def test_generate_skips_and_lists_a_damaged_combination(providers, repo, capsys):
    cli.main(["generate", "--model", "gpt", "--confirm-spend", "1"])
    damage(repo)
    capsys.readouterr()
    code = cli.main(["generate", "--model", "gpt", "--resume", "--confirm-spend", "1"])
    assert code == cli.EXIT_DATA_FAILURE
    err = capsys.readouterr().err
    assert "damaged: 2_B hybrid: inconsistent: attempt_1.json" in err
    assert "1 damaged combination(s) in data/suites/gpt were left as they are" in err
    assert providers["gpt"].calls_of("2_B", "hybrid") == 1


def test_report_and_package_refuse_a_damaged_tree(providers, repo, capsys):
    cli.main(["generate", "--model", "gpt", "--confirm-spend", "1"])
    damage(repo)
    assert cli.main(["report", "--model", "gpt"]) == cli.EXIT_DATA_FAILURE
    assert cli.main(["package", "--model", "gpt"]) == cli.EXIT_DATA_FAILURE
    assert "damaged: 2_B hybrid" in capsys.readouterr().err


def test_the_dry_run_lists_damage_too(providers, repo, capsys):
    cli.main(["generate", "--model", "gpt", "--confirm-spend", "1"])
    damage(repo)
    assert cli.main(["generate", "--model", "gpt", "--dry-run"]) == cli.EXIT_DATA_FAILURE
    assert "damaged: 2_B hybrid" in capsys.readouterr().err
