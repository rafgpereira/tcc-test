"""The public copy unzips the versioned packages into ``data/`` once, as the READMEs do by hand."""

import zipfile
from pathlib import Path

import pytest

from dashboard import cloud, config

REPO = Path(__file__).resolve().parents[2]

# Package -> one file inside it, in the layout of the real zips.
LAYOUT = {
    "evaluation_slm.zip": "evaluation/slm/problems/1_B/black_box.json",
    "evaluation_gpt.zip": "evaluation/gpt/problems/1_B/black_box.json",
    "evaluation_gemini.zip": "evaluation/gemini/problems/1_B/black_box.json",
    "evaluation_claude.zip": "evaluation/claude/problems/1_B/black_box.json",
    "evaluation_slm-attempt1.zip": "evaluation/slm-attempt1/problems/1_B/black_box.json",
    "metrics.zip": "metrics/metrics.csv",
    "dataset.zip": "dataset/problems/1_B/metadata.json",
    "mutants.zip": "mutants/problems/1_B/Mutant_1.cpp",
    "slm_suites.zip": "suites/slm/problems/1_B/black_box.json",
    "gpt_suites.zip": "suites/gpt/problems/1_B/black_box.json",
    "gemini_suites.zip": "suites/gemini/problems/1_B/black_box.json",
    "claude_suites.zip": "suites/claude/problems/1_B/black_box.json",
}


@pytest.fixture
def clone(tmp_path):
    """A fresh clone: ``data/`` has only the zips."""
    (tmp_path / "data").mkdir()
    for package in config.PUBLIC_PACKAGES:
        inner = LAYOUT[Path(package).name]
        with zipfile.ZipFile(tmp_path / package, "w") as archive:
            archive.writestr(inner, Path(package).name)
    return tmp_path


def test_every_public_package_is_versioned():
    assert {Path(p).name for p in config.PUBLIC_PACKAGES} == set(LAYOUT)
    assert all((REPO / p).is_file() for p in config.PUBLIC_PACKAGES)


def test_unzips_each_package_once_in_the_readme_layout(clone):
    assert cloud.prepare(clone) == list(config.PUBLIC_PACKAGES)
    for package, inner in LAYOUT.items():
        assert (clone / "data" / inner).read_text() == package
    # The suites of two models share ``suites/``; the evaluation of five sets, ``evaluation/``.
    assert sorted(p.name for p in (clone / "data/suites").iterdir()) == [
        "claude",
        "gemini",
        "gpt",
        "slm",
    ]
    assert not [p for p in (clone / "data").iterdir() if p.name.startswith("tmp")]
    assert cloud.prepare(clone) == []  # already there: nothing again


def test_a_package_with_two_top_folders_is_refused(clone):
    with zipfile.ZipFile(clone / config.PUBLIC_PACKAGES[0], "w") as archive:
        archive.writestr("a/x", "1")
        archive.writestr("b/y", "2")
    with pytest.raises(ValueError, match="one top folder"):
        cloud.prepare(clone)
