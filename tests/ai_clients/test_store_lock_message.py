"""The lock of a tree of suites names that tree; the message of the SLM is the same as before."""

import fcntl
from pathlib import Path

import pytest

from ai_clients import store


def test_the_slm_message_is_unchanged(repo):
    with (
        store.exclusive_run(repo),
        pytest.raises(store.AlreadyRunningError) as caught,
        store.exclusive_run(repo),
    ):
        pass
    assert str(caught.value) == (
        "another python -m ai_clients command is already running over data/suites/slm/"
    )


def test_a_lock_over_another_tree_names_it(repo):
    base = Path(repo) / "data" / "suites" / "gpt"
    gpt = Path("data/suites/gpt")
    with (
        store.lock_tree(repo, gpt, fcntl.LOCK_EX),
        pytest.raises(store.AlreadyRunningError) as caught,
        store.lock_tree(repo, gpt, fcntl.LOCK_SH),
    ):
        pass
    assert str(caught.value) == (
        "another python -m ai_clients command is already running over data/suites/gpt/"
    )
    assert (base / ".lock").is_file()


def test_two_trees_do_not_share_their_lock(repo):
    gpt, gemini = Path("data/suites/gpt"), Path("data/suites/gemini")
    with (
        store.lock_tree(repo, gpt, fcntl.LOCK_EX),
        store.lock_tree(repo, gemini, fcntl.LOCK_EX),
        store.exclusive_run(repo),
    ):
        pass


def test_a_combination_claimed_in_one_tree_is_free_in_another(repo):
    gpt, gemini = Path("data/suites/gpt"), Path("data/suites/gemini")
    with store.claim_in(repo, gpt, "1_A", "black_box") as mine:
        assert mine
        with store.claim_in(repo, gpt, "1_A", "black_box") as again:
            assert not again
        with store.claim_in(repo, gemini, "1_A", "black_box") as other:
            assert other
