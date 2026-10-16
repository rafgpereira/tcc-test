"""The core of the zip takes its paths as parameters; the SLM zip is the same as before."""

import zipfile
from pathlib import Path

from ai_clients import config, packaging


def _tree(base: Path) -> None:
    (base / "problems" / "1_A" / "black_box").mkdir(parents=True)
    (base / "problems" / "1_A" / "black_box" / "suite.json").write_text("{}\n")
    (base / "run.json").write_text('{"a": 1}\n')
    (base / ".lock").write_text("")
    (base / ".locks").mkdir()
    (base / "problems" / "1_A" / "black_box" / ".suite.json.x.tmp").write_text("partial")


def test_zip_tree_is_deterministic_and_skips_hidden_entries(tmp_path):
    base = tmp_path / "suites" / "gpt"
    _tree(base)
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    packaging.zip_tree(base, "suites/gpt", first)
    packaging.zip_tree(base, "suites/gpt", second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            "suites/gpt/",
            "suites/gpt/problems/",
            "suites/gpt/problems/1_A/",
            "suites/gpt/problems/1_A/black_box/",
            "suites/gpt/problems/1_A/black_box/suite.json",
            "suites/gpt/run.json",
        ]


def test_the_slm_root_gives_the_entries_the_slm_package_always_had(tmp_path):
    base = tmp_path / "slm"
    _tree(base)
    target = tmp_path / "slm.zip"
    packaging.zip_tree(base, config.ZIP_ROOT, target)
    with zipfile.ZipFile(target) as archive:
        assert all(name.startswith("suites/slm/") for name in archive.namelist())


def test_manifest_entries_hash_every_file_member(tmp_path):
    base = tmp_path / "gemini"
    _tree(base)
    target = tmp_path / "g.zip"
    packaging.zip_tree(base, "suites/gemini", target)
    entries = packaging.manifest_entries(target)
    assert [e.path for e in entries] == [
        "suites/gemini/problems/1_A/black_box/suite.json",
        "suites/gemini/run.json",
    ]
    assert entries[1].size == len('{"a": 1}\n')
