"""Shared fixtures of the ai_clients tests: a tiny packaged, manifested and extracted dataset."""

import json
import zipfile
from pathlib import Path

import pytest

from dataset import config as dataset_config
from dataset.integrity import manifest as manifest_module
from dataset.integrity import packaging
from dataset.persistence import store
from dataset.schemas.report import Provenance

PROVENANCE = Provenance(
    hf_dataset=dataset_config.HF_DATASET, hf_revision=dataset_config.HF_REVISION, seed=42
)

TIME_LIMIT_S = 1.0
MEMORY_LIMIT_BYTES = 268_435_456


def metadata_json(problem_id: str, *, time_limit: float = TIME_LIMIT_S) -> str:
    """A ``metadata.json`` that the dataset schema accepts."""
    contest, index = problem_id.split("_")
    return json.dumps(
        {
            "cf_contest_id": int(contest),
            "cf_index": index,
            "cf_points": 500.0,
            "cf_rating": 1500,
            "cf_tags": ["greedy"],
            "dataset_split_origem": "train",
            "extraction_timestamp": "2026-09-21T19:21:55Z",
            "is_description_translated": False,
            "macrocategoria": "logica_direta",
            "memory_limit_bytes": MEMORY_LIMIT_BYTES,
            "name": f"{problem_id}. Synthetic",
            "num_wa_brutos_disponiveis": 100,
            "num_wa_validados": 100,
            "problem_id": problem_id,
            "schema_version": 1,
            "source": "CODEFORCES",
            "time_limit_seconds": time_limit,
        }
    )


def testes_json(problem_id: str, public: list[tuple[str, str]]) -> str:
    """A ``testes.json`` with the given public tests and one private test."""
    return json.dumps(
        {
            "schema_version": 1,
            "problem_id": problem_id,
            "public_tests": [{"input": i, "output": o} for i, o in public],
            "private_tests": [{"input": "9\n", "output": "9\n"}],
            "generated_tests": [],
        }
    )


def problem(problem_id: str, public: list[tuple[str, str]] | None = None) -> dict[str, str]:
    """The files of one synthetic problem (echo problem: print the input number).

    The id appears in the statement and in a comment of ``AC_ref.cpp``, so the fake client can tell
    the problem of any prompt, whatever the scenario.
    """
    public = public if public is not None else [("1\n", "1\n"), ("2\n", "2\n")]
    return {
        "enunciado.md": f"# {problem_id}\n\nRead an integer n and print it.\n",
        "AC_ref.cpp": (
            f"// problem {problem_id}\n"
            "#include <iostream>\nint main(){long long n;std::cin>>n;std::cout<<n;}\n"
        ),
        "metadata.json": metadata_json(problem_id),
        "testes.json": testes_json(problem_id, public),
    }


def build_dataset(root: Path, problems: dict[str, dict[str, str]]) -> Path:
    """Write a packaged, manifested and extracted dataset under ``root`` (like a fresh clone).

    Same steps as ``build_dataset`` of ``tests/mutation/conftest.py``: every problem also gets the
    ``validacao.json`` the packager needs to consider it complete.
    """
    store.ensure_work_dir(root)
    for problem_id, files in problems.items():
        folder = store.start_building(root, problem_id)
        for name, content in files.items():
            store.write_problem_text(folder, name, content)
        store.write_problem_json(
            folder, "validacao.json", {"problem_id": problem_id, "status": "complete"}
        )
        store.finalize_building(root, problem_id)
    result = packaging.build_dataset_zip(root, root / "data" / "dataset.zip")
    manifest = manifest_module.build_manifest(root, result.zip_path, provenance=PROVENANCE)
    manifest_module.write_manifest(root, manifest)
    with zipfile.ZipFile(result.zip_path) as archive:
        archive.extractall(root / "data")
    return root


@pytest.fixture()
def problem_files() -> dict[str, dict[str, str]]:
    """Two synthetic problems, ``1_A`` and ``2_B``, each with two public tests."""
    return {"1_A": problem("1_A"), "2_B": problem("2_B")}


@pytest.fixture()
def repo(tmp_path, problem_files) -> Path:
    """A repository root with the two synthetic problems packaged, manifested and extracted."""
    return build_dataset(tmp_path, problem_files)
