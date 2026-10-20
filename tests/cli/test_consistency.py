"""Tests for `python -m cli check` (src/cli): the artifacts of the pipeline agree with each other.

Every test builds a small repository in ``tmp_path`` (3 problems, real rules: 100 WAs and 100
mutants each).
"""

import hashlib
import json
import shutil

import pytest

IDS = ["1000_B", "1005_C", "2_A"]


class Facade:
    """The library and the command line in one object."""

    def __init__(self):
        from cli import __main__ as entry
        from cli import consistency

        self._entry, self._lib = entry, consistency

    def main(self, argv):
        """``--root R [--only ..] [--deep]``: the command is always ``check``."""
        root_args, rest = [], list(argv)
        if "--root" in rest:
            i = rest.index("--root")
            root_args, rest = ["--root", rest[i + 1]], rest[:i] + rest[i + 2 :]
        return self._entry.main([*root_args, "check", *rest])

    def __getattr__(self, name):
        return getattr(self._lib, name)


@pytest.fixture()
def check():
    return Facade()


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


SCENARIOS = ("black_box", "white_box", "hybrid")
SLM_FILES = ["attempt_1.generation.json", "attempt_1.execution.json", "suite.json"]


def write_slm(root, ids=IDS, *, package=True):
    """A finished SLM run: every problem × scenario accepted at attempt 1, and its manifest."""
    files: list[dict] = []
    base = root / "data/suites/slm"
    base.mkdir(parents=True, exist_ok=True)
    (base / "run.json").write_text("run", encoding="utf-8")
    (base / ".lock").write_text("", encoding="utf-8")
    files.append({"path": "suites/slm/run.json", "size": 3, "sha256": sha("run")})
    for pid in ids:
        for scenario in SCENARIOS:
            folder = base / "problems" / pid / scenario
            folder.mkdir(parents=True)
            for name in SLM_FILES:
                text = f"{pid}/{scenario}/{name}"
                (folder / name).write_text(text, encoding="utf-8")
                path = f"suites/slm/problems/{pid}/{scenario}/{name}"
                files.append({"path": path, "size": len(text), "sha256": sha(text)})
    (root / "data" / "slm_suites.zip").write_bytes(b"zip-slm")
    if package:
        (root / "manifests" / "slm_suites.manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "slm_suites_zip": {
                        "path": "data/slm_suites.zip",
                        "size": 7,
                        "sha256": sha("zip-slm"),
                    },
                    "files": sorted(files, key=lambda f: f["path"]),
                }
            )
        )


LLM_FILES = ["attempt_1.json", "suite.json"]


def write_llm(root, model, ids=IDS, *, package=True):
    """A finished run of a commercial model: every problem × scenario accepted at attempt 1."""
    files: list[dict] = []
    base = root / "data/suites" / model
    base.mkdir(parents=True, exist_ok=True)
    (base / "run.json").write_text("run", encoding="utf-8")
    (base / ".lock").write_text("", encoding="utf-8")
    files.append({"path": f"suites/{model}/run.json", "size": 3, "sha256": sha("run")})
    for pid in ids:
        for scenario in SCENARIOS:
            folder = base / "problems" / pid / scenario
            folder.mkdir(parents=True)
            for name in LLM_FILES:
                text = f"{model}/{pid}/{scenario}/{name}"
                (folder / name).write_text(text, encoding="utf-8")
                path = f"suites/{model}/problems/{pid}/{scenario}/{name}"
                files.append({"path": path, "size": len(text), "sha256": sha(text)})
    zip_text = f"zip-{model}"
    (root / "data" / f"{model}_suites.zip").write_bytes(zip_text.encode())
    if package:
        (root / "manifests" / f"{model}_suites.manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "model_key": model,
                    "suites_zip": {
                        "path": f"data/{model}_suites.zip",
                        "size": len(zip_text),
                        "sha256": sha(zip_text),
                    },
                    "files": sorted(files, key=lambda f: f["path"]),
                }
            )
        )


def build(root, *, mutants=True, package=True, slm=True, llm=True):
    """A consistent repository: 3 problems, 105 files each, 100 mutants each, the suites of the
    three models for each problem × scenario, and their manifests."""
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
    if slm:
        write_slm(root, package=package)
    if llm:
        for model in ("gpt", "gemini", "claude"):
            write_llm(root, model, package=package)
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
    monkeypatch.setattr(check._lib, "LAYERS", (*check.LAYERS, layer))
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "todo problema de dataset tem pasta em ia: 2/3" in out


# -------------------------------------------------------------------------------- slm_suites layer


def slm_folder(root, pid="1000_B", scenario=None):
    base = root / "data/suites/slm/problems" / pid
    return base / scenario if scenario else base


def unpackaged(root):
    (root / "manifests" / "slm_suites.manifest.json").unlink()
    return root


def test_a_finished_slm_run_passes_with_its_counts(check, repo, capsys):
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 0
    assert "black_box, white_box e hybrid: 3/3" in out
    assert "tentativas numeradas sem buraco, no máximo 15 (execuções até a 12ª): 9/9" in out
    assert "suite.json em cada cenário: 9/9" in out
    assert "todo problema de dataset tem pasta em slm_suites: 3/3" in out
    assert "nomes dos arquivos batem com o manifesto (28 arquivos)" in out
    assert "hash SHA-256 de 28 arquivo(s) confere" in out
    assert "data/slm_suites.zip: hash confere" in out


def test_no_slm_run_yet_is_only_a_warning(check, tmp_path, capsys):
    build(tmp_path, slm=False)
    code, out = run(check, tmp_path, "--deep", capsys=capsys)
    assert code == 0 and "[AVISO] a pasta data/suites/slm/problems ainda não existe" in out


def test_a_run_in_progress_is_a_warning_even_with_deep(check, repo, capsys):
    """Before `package` (no manifest) missing folders and suites are the run in progress."""
    unpackaged(repo)
    shutil.rmtree(slm_folder(repo, "2_A"))
    shutil.rmtree(slm_folder(repo, "1005_C", "hybrid"))
    (slm_folder(repo, "1000_B", "white_box") / "suite.json").unlink()
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 0
    assert "[AVISO] black_box, white_box e hybrid: 1/2" in out
    assert "[AVISO] suite.json em cada cenário: 4/5" in out
    assert "[AVISO] todo problema de dataset tem pasta em slm_suites: 2/3" in out


@pytest.mark.parametrize("deep", [False, True])
def test_after_package_everything_must_be_there(check, repo, capsys, deep):
    (slm_folder(repo, "1000_B", "white_box") / "suite.json").unlink()
    shutil.rmtree(slm_folder(repo, "2_A"))
    code, out = run(check, repo, *(["--deep"] if deep else []), capsys=capsys)
    assert code == 1
    assert "[FALHA] suite.json em cada cenário: 5/6" in out
    assert "[FALHA] todo problema de dataset tem pasta em slm_suites: 2/3" in out


def test_a_missing_scenario_after_package_is_a_failure(check, repo, capsys):
    shutil.rmtree(slm_folder(repo, "1005_C", "hybrid"))
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "[FALHA] black_box, white_box e hybrid: 2/3" in out and "1005_C" in out


def test_an_slm_folder_without_a_problem_is_a_failure(check, repo, capsys):
    unpackaged(repo)
    (slm_folder(repo, "9_Z") / "black_box").mkdir(parents=True)
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "nenhuma pasta de slm_suites sem problema em dataset: 1 sobrando" in out


def _sixteen_attempts(folder):
    for n in range(2, 17):
        (folder / f"attempt_{n}.generation.json").write_text("x")


def _execution_of_a_prediction(folder):
    for n in range(2, 14):
        (folder / f"attempt_{n}.generation.json").write_text("x")
    (folder / "attempt_13.execution.json").write_text("x")


@pytest.mark.parametrize(
    "make",
    [
        lambda f: (f / "attempt_3.generation.json").write_text("x"),
        lambda f: (f / "attempt_2.execution.json").write_text("x"),
        _sixteen_attempts,
        _execution_of_a_prediction,
    ],
    ids=[
        "gap",
        "execution_without_generation",
        "sixteen_attempts",
        "execution_of_a_prediction",
    ],
)
def test_attempts_with_a_gap_or_beyond_15_are_a_failure(check, repo, capsys, make):
    unpackaged(repo)
    make(slm_folder(repo, "1000_B", "black_box"))
    code, out = run(check, repo, capsys=capsys)
    assert code == 1
    assert "[FALHA] tentativas numeradas sem buraco, no máximo 15 (execuções até a 12ª): 8/9" in out
    assert "1000_B/black_box" in out


def test_manual_close_json_is_a_known_file(check, repo, capsys):
    unpackaged(repo)
    (slm_folder(repo, "2_A", "hybrid") / "manual_close.json").write_text("x")
    _, out = run(check, repo, capsys=capsys)
    assert "arquivo(s) estranho(s)" not in out


def test_an_unknown_file_in_a_scenario_is_a_failure(check, repo, capsys):
    unpackaged(repo)
    (slm_folder(repo, "2_A", "hybrid") / "notes.txt").write_text("x")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "2_A/hybrid: notes.txt" in out


def test_deep_finds_a_changed_byte_in_an_slm_file(check, repo, capsys):
    path = slm_folder(repo, "2_A", "hybrid") / "suite.json"
    path.write_text(path.read_text(encoding="utf-8").upper(), encoding="utf-8")
    assert run(check, repo, capsys=capsys)[0] == 0  # names still match
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 1 and "1 arquivo(s) com conteúdo diferente do manifesto" in out


def test_no_slm_manifest_yet_is_a_warning(check, repo, capsys):
    unpackaged(repo)
    code, out = run(check, repo, "--deep", capsys=capsys)
    assert code == 0
    assert "manifests/slm_suites.manifest.json ainda não existe (pacote não gerado)" in out


def test_a_packaged_run_must_be_extracted(check, repo, capsys):
    shutil.rmtree(repo / "data/suites")
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "[FALHA] a pasta data/suites/slm/problems não existe" in out


def test_only_slm_suites(check, repo, capsys):
    shutil.rmtree(repo / "data/mutants")
    code, out = run(check, repo, "--only", "dataset,slm_suites", capsys=capsys)
    assert code == 0 and "Mutant_" not in out and "slm_suites" in out


# ----------------------------------------------------------------- gpt_suites and gemini_suites


def llm_folder(root, model, pid="1000_B", scenario=None):
    base = root / "data/suites" / model / "problems" / pid
    return base / scenario if scenario else base


@pytest.mark.parametrize("model", ["gpt", "gemini", "claude"])
def test_a_finished_llm_run_passes_with_its_counts(check, repo, capsys, model):
    code, out = run(check, repo, "--deep", "--only", f"{model}_suites", capsys=capsys)
    assert code == 0
    assert "tentativas numeradas sem buraco, no máximo 3: 9/9" in out
    assert "suite.json em cada cenário: 9/9" in out
    code, everything = run(check, repo, "--deep", capsys=capsys)
    assert code == 0 and f"todo problema de dataset tem pasta em {model}_suites: 3/3" in everything
    assert "nomes dos arquivos batem com o manifesto (19 arquivos)" in out
    assert f"data/{model}_suites.zip: hash confere" in out


def test_no_llm_run_yet_is_only_a_warning(check, tmp_path, capsys):
    build(tmp_path, llm=False)
    code, out = run(check, tmp_path, capsys=capsys)
    assert code == 0
    assert "[AVISO] a pasta data/suites/gpt/problems ainda não existe" in out
    assert "[AVISO] a pasta data/suites/gemini/problems ainda não existe" in out
    assert "[AVISO] a pasta data/suites/claude/problems ainda não existe" in out


def test_an_llm_run_in_progress_is_a_warning(check, repo, capsys):
    (repo / "manifests" / "gpt_suites.manifest.json").unlink()
    (llm_folder(repo, "gpt", "2_A", "hybrid") / "suite.json").unlink()
    code, out = run(check, repo, "--only", "gpt_suites", capsys=capsys)
    assert code == 0 and "[AVISO] suite.json em cada cenário: 8/9" in out


def test_after_the_package_of_one_model_its_suites_must_be_there(check, repo, capsys):
    (llm_folder(repo, "gemini", "2_A", "hybrid") / "suite.json").unlink()
    code, out = run(check, repo, capsys=capsys)
    assert code == 1 and "[FALHA] suite.json em cada cenário: 8/9" in out


@pytest.mark.parametrize(
    "files, message",
    [
        (["attempt_4.json"], "tentativas numeradas sem buraco, no máximo 3: 8/9"),
        (["attempt_3.json"], "tentativas numeradas sem buraco, no máximo 3: 8/9"),
        (["notes.txt"], "1 arquivo(s) estranho(s) num cenário"),
        (["attempt_1.generation.json"], "1 arquivo(s) estranho(s) num cenário"),
    ],
)
def test_attempts_beyond_three_gaps_and_strange_files_always_fail(
    check, repo, capsys, files, message
):
    (repo / "manifests" / "gpt_suites.manifest.json").unlink()
    for name in files:
        (llm_folder(repo, "gpt", "1000_B", "black_box") / name).write_text("x")
    code, out = run(check, repo, "--only", "gpt_suites", capsys=capsys)
    assert code == 1 and f"[FALHA] {message}" in out


def test_barred_answers_are_checked_apart(check, repo, capsys):
    (repo / "manifests" / "gpt_suites.manifest.json").unlink()
    barred = repo / "data/suites/gpt/barred"
    (barred / "1000_B" / "hybrid").mkdir(parents=True)
    (barred / "1000_B" / "hybrid" / "1.json").write_text("{}")
    code, out = run(check, repo, "--only", "gpt_suites", capsys=capsys)
    assert code == 0 and "respostas barradas por falta de raciocínio: 1" in out
    (barred / "9_Z" / "hybrid").mkdir(parents=True)
    (barred / "9_Z" / "hybrid" / "1.json").write_text("{}")
    code, out = run(check, repo, "--only", "gpt_suites", capsys=capsys)
    assert code == 1 and "[FALHA] barred/ só tem respostas de problema e cenário existentes" in out


def test_the_old_layers_keep_their_output(check, repo, capsys):
    code, out = run(check, repo, "--only", "slm_suites", capsys=capsys)
    assert code == 0 and "gpt" not in out and "gemini" not in out


def test_the_claude_layer_has_its_title_and_its_own_only(check, repo, capsys):
    code, out = run(check, repo, "--only", "claude_suites", capsys=capsys)
    assert code == 0 and "Suítes do Claude Haiku 5.5 (data/suites/claude/problems)" in out
    assert "Suítes do GPT" not in out and "Suítes do Gemini" not in out
