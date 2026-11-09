"""Fixed configuration of the evaluation module (docs/metodologia-referencia.md, section 4).

There is no randomness anywhere: the order of the tests is the order of the suite, and the order of
the targets is ``WA_1..WA_100`` then ``Mutant_1..Mutant_100``.
"""

from pathlib import Path

# The evaluation sets: the final suites of the four models and the first attempt of the local one.
SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")
FINAL_SETS = ("slm", "gpt", "gemini", "claude")
SET_MODEL = {"slm": "slm", "gpt": "gpt", "gemini": "gemini", "claude": "claude"}
SET_MODEL["slm-attempt1"] = "slm"
SET_ATTEMPT = {"slm-attempt1": 1}  # the only isolated attempt that is evaluated
SCENARIOS = ("black_box", "white_box", "hybrid")

# A runtime error (RE, TLE or MLE) is run this many times in total before it counts (FR-005a,
# FR-006a): the 2 repetitions are always made.
ERROR_RUNS = 3

# Targets per problem (dataset and mutants); the report says a set is complete only with these.
WA_PER_PROBLEM = 100
MUTANTS_PER_PROBLEM = 100

PILOT_PROBLEMS = ("1000_B", "1005_C", "1008_B", "1_B", "61_B")

# Layout under the repository root. Nothing under `data/evaluation/` is versioned; only the packaged
# result of the final run is (Constitution, Principle II).
DATA_DIR = Path("data")
DATASET_PROBLEMS_DIR = DATA_DIR / "dataset" / "problems"
MUTANTS_PROBLEMS_DIR = DATA_DIR / "mutants" / "problems"
SUITES_DIR = DATA_DIR / "suites"
SLM_PROVENANCE = SUITES_DIR / "slm" / "provenance.json"
EVALUATION_DIR = DATA_DIR / "evaluation"
MANIFESTS_DIR = Path("manifests")
DATASET_MANIFEST = MANIFESTS_DIR / "dataset.manifest.json"
MUTANTS_MANIFEST = MANIFESTS_DIR / "mutants.manifest.json"

LOCK_FILE = ".lock"
RUN_FILE = "run.json"
RESULTS_CSV = "results.csv"
BUILDING = "building"
PROBLEMS = "problems"
SUITE_FILE = "suite.json"


def suites_manifest(model: str) -> Path:
    return MANIFESTS_DIR / f"{model}_suites.manifest.json"


def zip_path(set_name: str) -> Path:
    return DATA_DIR / f"evaluation_{set_name}.zip"


def manifest_path(set_name: str) -> Path:
    return MANIFESTS_DIR / f"evaluation_{set_name}.manifest.json"


def report_path(set_name: str) -> Path:
    return MANIFESTS_DIR / f"evaluation_{set_name}_report.json"


def layer_key(set_name: str) -> str:
    """The key of the set's layer in ``python -m cli check``."""
    return "evaluation_" + set_name.replace("-", "_")


def scenario_file(scenario: str) -> str:
    return f"{scenario}.json"
