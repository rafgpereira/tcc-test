"""Tests for scripts/check_consistency.py: the artifacts of the pipeline agree with each other.

Every test builds a small repository in ``tmp_path`` (3 problems, real rules: 100 WAs and 100
mutants each) and loads the script with ``importlib`` (``scripts/`` is not a package).
"""

import hashlib
import importlib.util
import json
import shutil
import sys

import pytest

IDS = ["1000_B", "1005_C", "2_A"]


@pytest.fixture(scope="module")
def check(repo_root):
    path = repo_root / "scripts" / "check_consistency.py"
    spec = importlib.util.spec_from_file_location("check_consistency", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DATASET_FILES = ["AC_ref.cpp", "enunciado.md", "metadata.json", "testes.json", "validacao.json"] + [
    f"WA_{i}.cpp" for i in range(1, 101)
]
MUTANT_FILES = [f"Mutant_{i}.cpp" for i in range(1, 101)]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_tree(root, layer_root, prefix, ids, names, manifest_files):
    """Write ``<layer_root>/<id>/<name>`` and record each file for the manifest."""
    for pid in ids:
        folder = root / layer_root / pid
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            text = f"{pid}/{name}"
            (folder / name).write_text(text, encoding="utf-8")
            manifest_files.append(
                {"path": f"{prefix}{pid}/{name}", "size": len(text), "sha256": sha(text)}
            )


def build(root, *, mutants=True, package=True):
    """A consistent repository: 3 problems, 105 files each, 100 mutants each, both manifests."""
    (root / "manifests").mkdir(parents=True)
    files: list[dict] = []
    write_tree(root, "data/dataset/problems", "dataset/problems/", IDS, DATASET_FILES, files)
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "dataset.zip").write_bytes(b"zip-dataset")
    manifest = {
        "schema_version": 1,
        "dataset_zip": {"path": "data/dataset.zip", "size": 11, "sha256": sha("zip-dataset")},
        "files": sorted(files, key=lambda f: f["path"]),
        "problem_count": len(IDS),
    }
    (root / "manifests" / "dataset.manifest.json").write_text(json.dumps(manifest))
    if mutants:
        mfiles: list[dict] = []
        write_tree(root, "data/mutants/problems", "mutants/problems/", IDS, MUTANT_FILES, mfiles)
        for pid in IDS:
            (root / "data/mutants/problems" / pid / "generation.json").write_text("{}")
        (root / "data" / "mutants.zip").write_bytes(b"zip-mutants")
        if package:
            (root / "manifests" / "mutants.manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mutants_zip": {
                            "path": "data/mutants.zip",
                            "size": 11,
                            "sha256": sha("zip-mutants"),
                        },
                        "files": sorted(mfiles, key=lambda f: f["path"]),
                    }
                )
            )
    return root


@pytest.fixture()
def repo(tmp_path):
    return build(tmp_path)


def run(check, root, *args, capsys=None):
    code = check.main(["--root", str(root), *args])
    return code, (capsys.readouterr().out if capsys else "")


def statuses(report):
    return [(s.title, l.status, l.text) for s in report.sections for l in s.lines]


# --------------------------------------------------------------------------------- happy path


def test_a_consistent_repository_passes_with_the_counts_in_the_summary(check, repo, capsys):
    code, out = run(check, repo, capsys=capsys)
    assert code == 0 and "Resultado: OK (0 falha(s)" in out
    assert "pastas de problema: 3 (o manifesto diz 3)" in out
    assert "AC_ref.cpp: 3/3" in out and "WA_1.cpp a WA_100.cpp: 3/3" in out
    assert "Mutant_1.cpp a Mutant_100.cpp: 3/3" in out
    assert "todo problema de dataset tem pasta em mutants: 3/3" in out
    assert "nomes dos arquivos batem com o manifesto (315 arquivos)" in out


def test_deep_recomputes_the_hashes_and_passes_on_a_consistent_repository(check, repo, capsys):
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 0
    assert (
        "hash SHA-256 de 315 arquivo(s) confere" in out and "hash SHA-256 de 300 arquivo(s)" in out
    )
    assert "data/dataset.zip: hash confere" in out and "data/mutants.zip: hash confere" in out


# ------------------------------------------------------------------------------ dataset layer


def dataset_folder(root, pid="1000_B"):
    return root / "data/dataset/problems" / pid


@pytest.mark.parametrize(
    "name", ["AC_ref.cpp", "enunciado.md", "metadata.json", "testes.json", "validacao.json"]
)
def test_a_missing_fixed_file_is_a_failure_naming_the_problem(check, repo, capsys, name):
    (dataset_folder(repo) / name).unlink()
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and f"{name}: 2/3" in out and "1000_B" in out


def test_ninety_nine_wa_files_is_a_failure(check, repo, capsys):
    (dataset_folder(repo) / "WA_50.cpp").unlink()
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "WA_1.cpp a WA_100.cpp: 2/3" in out


def test_a_wa_numbered_out_of_range_is_an_unexpected_file(check, repo, capsys):
    (dataset_folder(repo) / "WA_101.cpp").write_text("x")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "nenhum arquivo além dos esperados: 2/3" in out and "WA_101.cpp" in out


def test_an_extra_file_in_a_problem_folder_is_a_failure(check, repo, capsys):
    (dataset_folder(repo, "2_A") / "notas.txt").write_text("x")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "2_A: notas.txt" in out


def test_the_problem_count_must_match_the_manifest(check, repo, capsys):
    shutil.rmtree(dataset_folder(repo, "2_A"))
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "pastas de problema: 2 (o manifesto diz 3)" in out


def test_a_folder_that_is_not_a_problem_is_reported(check, repo, capsys):
    (repo / "data/dataset/problems/lixo").mkdir()
    (repo / "data/dataset/problems/README.txt").write_text("x")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "2 entrada(s) que não é pasta de problema" in out


def test_dot_files_are_ignored(check, repo, capsys):
    (repo / "data/dataset/problems/.gitkeep").write_text("")
    (dataset_folder(repo) / ".hidden").write_text("")
    assert run(check, repo, capsys=capsys)[0] == 0


def test_names_that_differ_from_the_manifest_are_reported_both_ways(check, repo, capsys):
    (dataset_folder(repo) / "enunciado.md").rename(dataset_folder(repo) / "statement.md")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1
    assert "NÃO batem com o manifesto" in out
    assert "faltam no disco (1)" in out and "sobram no disco (1)" in out


def test_a_missing_dataset_folder_is_a_failure(check, repo, capsys):
    shutil.rmtree(repo / "data/dataset")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "a pasta data/dataset/problems não existe" in out


def test_a_missing_dataset_manifest_is_a_usage_error(check, repo, capsys):
    (repo / "manifests/dataset.manifest.json").unlink()
    assert check.main(["--root", str(repo)]) == 2
    assert "manifest not found" in capsys.readouterr().err


# ------------------------------------------------------------------------------ mutants layer


def mutants_folder(root, pid="1000_B"):
    return root / "data/mutants/problems" / pid


def test_ninety_nine_mutants_is_a_failure(check, repo, capsys):
    (mutants_folder(repo) / "Mutant_37.cpp").unlink()
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "Mutant_1.cpp a Mutant_100.cpp: 2/3" in out and "1000_B" in out


def test_a_hundred_and_first_mutant_is_a_failure(check, repo, capsys):
    (mutants_folder(repo) / "Mutant_101.cpp").write_text("x")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "Mutant_101.cpp" in out


def test_generation_json_is_allowed_and_not_required(check, repo, capsys):
    (mutants_folder(repo) / "generation.json").unlink()
    assert run(check, repo, capsys=capsys)[0] == 0


def test_a_problem_excluded_for_lack_of_mutants_is_a_warning_not_a_failure(check, tmp_path, capsys):
    build(tmp_path, package=False)  # before packaging, as right after `generate`
    folder = mutants_folder(tmp_path, "2_A")
    for name in MUTANT_FILES:
        (folder / name).unlink()
    (folder / "generation.json").write_text(json.dumps({"status": "excluded"}))
    code, out = run(check, tmp_path, "--only", "mutants", capsys=capsys)
    assert code == 0 and "[AVISO]" in out and "1 problema(s) excluído(s)" in out
    assert "Mutant_1.cpp a Mutant_100.cpp: 2/2" in out


def test_a_problem_left_in_building_is_a_failure(check, repo, capsys):
    (repo / "data/mutants/building/1000_B").mkdir(parents=True)
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "1 problema(s) pela metade em data/mutants/building" in out


def test_no_mutants_manifest_yet_is_only_a_warning(check, tmp_path, capsys):
    build(tmp_path, package=False)
    code, out = run(check, tmp_path, capsys=capsys)
    assert code == 0 and "ainda não existe (pacote não gerado)" in out


def test_a_mutant_the_manifest_lists_but_the_disk_lacks_is_a_failure(check, repo, capsys):
    (mutants_folder(repo) / "Mutant_5.cpp").unlink()
    code, out = run(check, repo, capsys=capsys)
    assert (
        code == 1 and "faltam no disco (1)" in out and "mutants/problems/1000_B/Mutant_5.cpp" in out
    )


# --------------------------------------------------------------------------------- relation


def test_a_dataset_problem_without_mutants_is_a_failure(check, repo, capsys):
    shutil.rmtree(mutants_folder(repo, "2_A"))
    code, out = run(check, repo, capsys=capsys)
    assert (
        code == 1 and "todo problema de dataset tem pasta em mutants: 2/3" in out and "2_A" in out
    )


def test_mutants_without_a_problem_in_the_dataset_are_a_failure(check, repo, capsys):
    shutil.copytree(mutants_folder(repo), repo / "data/mutants/problems/9_Z")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "nenhuma pasta de mutants sem problema em dataset: 1 sobrando" in out
    assert "9_Z" in out


def test_a_missing_mutants_folder_is_a_failure_when_mutants_are_checked(check, tmp_path, capsys):
    build(tmp_path, mutants=False)
    code, out = run(check, tmp_path, capsys=capsys)
    assert code == 1 and "a pasta data/mutants/problems não existe" in out


def test_only_dataset_ignores_the_mutants(check, tmp_path, capsys):
    build(tmp_path, mutants=False)
    code, out = run(check, tmp_path, "--only", "dataset", capsys=capsys)
    assert code == 0 and "Mutantes" not in out and "Relação 1:1" not in out


def test_an_unknown_layer_is_a_usage_error(check, repo, capsys):
    assert check.main(["--root", str(repo), "--only", "ia"]) == 2
    assert "unknown layer" in capsys.readouterr().err


# ------------------------------------------------------------------------------------ --deep


def test_deep_finds_a_changed_byte_that_the_names_do_not_show(check, repo, capsys):
    (dataset_folder(repo) / "AC_ref.cpp").write_text("edited!")
    assert run(check, repo, capsys=capsys)[0] == 0  # names alone cannot see it
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 1 and "1 arquivo(s) com conteúdo diferente do manifesto" in out
    assert "dataset/problems/1000_B/AC_ref.cpp" in out


def test_deep_finds_a_changed_mutant(check, repo, capsys):
    (mutants_folder(repo, "2_A") / "Mutant_9.cpp").write_text("edited")
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 1 and "mutants/problems/2_A/Mutant_9.cpp" in out


def test_deep_finds_a_zip_that_differs_from_the_manifest(check, repo, capsys):
    (repo / "data/dataset.zip").write_bytes(b"another zip")
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 1 and "data/dataset.zip: hash DIFERE" in out


def test_deep_without_the_zip_is_only_a_warning(check, repo, capsys):
    (repo / "data/mutants.zip").unlink()
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 0 and "data/mutants.zip não existe" in out


def test_the_report_object_is_usable_from_code(check, repo):
    report = check.run_checks(repo)
    assert report.ok and report.failures == 0 and report.warnings == 0
    assert [s.title for s in report.sections][-1] == "Relação 1:1 entre as camadas"


def test_long_lists_of_offenders_are_cut(check, repo, capsys):
    for i in range(100, 116):
        (repo / f"data/dataset/problems/{i}_A").mkdir()
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "... e mais" in out


def test_a_new_layer_is_checked_and_related_with_no_change_to_the_checks(
    check, repo, capsys, monkeypatch
):
    """Later modules add a Layer (here: tests generated by an AI) and get the 1:1 check for free."""
    write_tree(repo, "data/ai_tests/problems", "ai/", IDS[:2], ["teste_1.cpp"], [])
    layer = check.Layer(
        key="ia",
        title="Testes da IA",
        root="data/ai_tests/problems",
        groups=(check.Group("teste_1.cpp", frozenset({"teste_1.cpp"})),),
        allowed_extra=frozenset(),
        manifest=None,
        manifest_required=False,
        manifest_prefix="ai/",
    )
    monkeypatch.setattr(check, "LAYERS", (*check.LAYERS, layer))
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "todo problema de dataset tem pasta em ia: 2/3" in out
