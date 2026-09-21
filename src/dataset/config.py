"""Fixed configuration of the dataset module.

Every constant here is part of the experiment design (docs/metodologia-referencia.md, section 1).
Changing one after the first extraction changes the selection of problems.
"""

import random
from pathlib import Path

# Randomness (Constitution, Principle II): one fixed, documented seed; a stream per context.
SEED = 42

# Source dataset, read through streaming on a pinned revision (spec FR-001, decision D12).
HF_DATASET = "deepmind/code_contests"
HF_REVISION = "802411c3010cb00d1b05bad57ca77365a3c699d6"
HF_SOURCE_CODEFORCES = 2  # ClassLabel index of `source`
HF_LANGUAGE_CPP = 2  # ClassLabel index of `language`

# Splits in the order they are read; the first occurrence of a problem wins (spec FR-002, FR-003).
SPLITS = ("train", "valid", "test")

# Sample size and validation (spec FR-014, FR-016, FR-018a).
TARGET_PROBLEMS = 200
WA_PER_PROBLEM = 100
CATEGORY_ALERT_THRESHOLD = 30
STABILITY_RUNS = 2
# Reopening criterion of decision D13 (rules 2 and 5): in the pilot, more than this fraction of the
# ACs tested rejected only for formatting, or only for TLE, sends that rule back to the authors.
AC_REOPEN_THRESHOLD = 0.10

# Eligibility (spec FR-004).
RATING_MIN = 1000
RATING_MAX = 1600
ALLOWED_TAGS = frozenset(
    {"implementation", "math", "greedy", "strings", "binary search", "dp", "sortings"}
)
FORBIDDEN_TAGS = frozenset(
    {"geometry", "interactive", "games", "probabilities", "constructive algorithms"}
)
VISUAL_TERMS = (
    "figure",
    "image",
    "picture",
    "shown below",
    "as follows",
    "http",
    ".png",
    ".jpg",
)

# Eligibility stages in the order of the funnel (methodology 1.2). The stored JSON has sorted keys,
# so consumers that list the stages (the report) must use this order, not the order of the file.
FUNNEL_STAGES = (
    "codeforces",
    "rating_1000_1600",
    "has_allowed_tag",
    "no_forbidden_tag",
    "no_visual_term",
    "not_translated",
    "unique_id",
    "no_file_io",
    "has_cpp_solutions",
    "enough_raw_wa",
)

# Layout under the repository root. `data/work/` is private (mode 0700, spec decision D15).
DATA_DIR = Path("data")
WORK_DIR = DATA_DIR / "work"
STAGING_DIR = WORK_DIR / "staging"
RAW_DIR = STAGING_DIR / "raw"
SHARDS_DIR = STAGING_DIR / "shards"
BUILDING_DIR = WORK_DIR / "building"
PROBLEMS_DIR = WORK_DIR / "problems"
REPORTS_DIR = WORK_DIR / "reports"
# Subdirectories of data/work/, relative to it, in creation order.
WORK_SUBDIRS = ("staging", "staging/raw", "staging/shards", "building", "problems", "reports")

DATASET_ZIP = DATA_DIR / "dataset.zip"
MANIFEST_PATH = Path("manifests") / "dataset.manifest.json"


def seeded_random(context: str, seed: int = SEED) -> random.Random:
    """Return the random stream of a context, e.g. ``"pool"`` or ``"wa:1101_A"``.

    The textual seed does not depend on ``PYTHONHASHSEED``, so the stream is reproducible.
    """
    return random.Random(f"{seed}:{context}")
