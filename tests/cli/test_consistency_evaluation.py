"""The layers of the evaluation sets in ``cli check`` (specs/009, T032)."""

import json

import pytest

from cli import consistency
from tests.cli.test_consistency import IDS, SCENARIOS, build, sha

LAYER = "evaluation_gpt"


def write_evaluation(root, set_name="gpt", ids=IDS, *, package=True):
    """A finished evaluation set: three scenario files per problem, run.json, results.csv."""
    base = root / "data/evaluation" / set_name
    files = []

    def put(rel, text):
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append(
            {"path": f"evaluation/{set_name}/{rel}", "size": len(text), "sha256": sha(text)}
        )

    put("run.json", "run")
    put("results.csv", "csv")
    for pid in ids:
        for scenario in SCENARIOS:
            put(f"problems/{pid}/{scenario}.json", f"{pid}/{scenario}")
    (base / "building").mkdir()
    (root / "data/evaluation/.lock").write_text("")
    zip_text = f"zip-{set_name}"
    (root / f"data/evaluation_{set_name}.zip").write_text(zip_text)
    if package:
        (root / f"manifests/evaluation_{set_name}.manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "set": set_name,
                    "evaluation_zip": {
                        "path": f"data/evaluation_{set_name}.zip",
                        "size": len(zip_text),
                        "sha256": sha(zip_text),
                    },
                    "files": sorted(files, key=lambda f: f["path"]),
                }
            )
        )
    return base


def lines(root, only=(LAYER,), deep=False):
    report = consistency.run_checks(root, ["dataset", *only], deep)
    return report, [(l.status, l.text) for s in report.sections for l in s.lines]


@pytest.fixture()
def repo(tmp_path):
    return build(tmp_path)


def test_there_is_one_layer_per_evaluation_set():
    keys = [layer.key for layer in consistency.LAYERS]
    assert keys[-5:] == [
        "evaluation_slm",
        "evaluation_gpt",
        "evaluation_gemini",
        "evaluation_claude",
        "evaluation_slm_attempt1",
    ]


def test_an_absent_evaluation_is_only_a_warning(repo):
    report, found = lines(repo)
    assert report.ok
    assert any(status == consistency.WARN and "ainda não existe" in text for status, text in found)


def test_a_packaged_evaluation_passes_with_deep(repo):
    write_evaluation(repo)
    report, found = lines(repo, deep=True)
    assert report.ok, report.render()
    assert (consistency.OK, "nomes dos arquivos batem com o manifesto (11 arquivos)") in found


def test_a_missing_scenario_is_a_warning_before_the_package_and_a_failure_after(repo):
    base = write_evaluation(repo, package=False)
    (base / "problems/2_A/hybrid.json").unlink()
    report, _ = lines(repo)
    assert report.ok and report.warnings
    base = write_evaluation(repo, "claude")
    (base / "problems/2_A/hybrid.json").unlink()
    report, _ = lines(repo, only=("evaluation_claude",))
    assert not report.ok


def test_a_strange_file_and_a_problem_outside_the_dataset_always_fail(repo):
    base = write_evaluation(repo, package=False)
    (base / "problems/1000_B/notes.txt").write_text("x")
    report, _ = lines(repo)
    assert not report.ok
    (base / "problems/1000_B/notes.txt").unlink()
    (base / "problems/9_Z").mkdir()
    for scenario in SCENARIOS:
        (base / f"problems/9_Z/{scenario}.json").write_text("{}")
    report, found = lines(repo)
    assert not report.ok
    assert any("sem problema em dataset: 1 sobrando" in text for _, text in found)


def test_something_left_in_building_after_the_package_fails(repo):
    base = write_evaluation(repo)
    (base / "building/1000_B").mkdir()
    (base / "building/1000_B/black_box.json").write_text("{}")
    report, _ = lines(repo)
    assert not report.ok


def test_deep_detects_a_changed_result(repo):
    base = write_evaluation(repo)
    (base / "problems/1000_B/black_box.json").write_text("changed")
    report, _ = lines(repo, deep=True)
    assert not report.ok
