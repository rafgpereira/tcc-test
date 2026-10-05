"""Fixed configuration of the mutation module.

Every constant here is part of the experiment design (docs/metodologia-referencia.md, section 2).
There is deliberately NO seed: this module uses no randomness at all (decision D6); every order
comes from the traversal of the syntax tree.
"""

from pathlib import Path

# Quota and naming (spec FR-003, FR-003a; research R6).
MUTANTS_PER_PROBLEM = 100
MUTANT_FILE_PREFIX = "Mutant_"  # never `WA_`: a mutant must not be mistaken for a real failure
MUTANT_FILE_SUFFIX = ".cpp"

# Agreeing runs of the same compiled mutant before it is accepted (spec FR-007, decision D5).
STABILITY_RUNS = 6

# Highest order of the deterministic combination of mutations (spec FR-004).
HOM_MAX_ORDER = 3

# Layout under the repository root. Nothing under `data/mutants/` is ever versioned; only the
# packaged result of the final run is (Constitution, Principle II, amendment 1.6.0).
DATA_DIR = Path("data")
DATASET_DIR = DATA_DIR / "dataset"
DATASET_PROBLEMS_DIR = DATASET_DIR / "problems"
MUTANTS_DIR = DATA_DIR / "mutants"
BUILDING_DIR = MUTANTS_DIR / "building"
PROBLEMS_DIR = MUTANTS_DIR / "problems"

MUTANTS_ZIP = DATA_DIR / "mutants.zip"
MANIFEST_PATH = Path("manifests") / "mutants.manifest.json"
REPORT_PATH = Path("manifests") / "mutation_report.json"
DATASET_MANIFEST_PATH = Path("manifests") / "dataset.manifest.json"

# Record kept next to the mutants of a problem (never packaged): how they were reached.
GENERATION_FILE = "generation.json"
LOCK_FILE = ".lock"  # flock: one `generate` at a time over data/mutants/


def mutant_file_name(index: int) -> str:
    """``Mutant_<index>.cpp`` (index starts at 1, in the order of acceptance)."""
    return f"{MUTANT_FILE_PREFIX}{index}{MUTANT_FILE_SUFFIX}"
