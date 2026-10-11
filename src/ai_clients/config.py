"""Fixed configuration of the SLM test-suite generation (docs/metodologia-referencia.md, section 3).

Every constant here is part of the experiment design. The only values the operator sets are the
address of the Ollama server, the hardware label and, optionally, how long to wait for an answer,
how many consecutive infrastructure failures to tolerate and another model for a pilot; they come
from ``.env`` (names below), never from this file. The time and memory limits of the Python
reference solution are NEVER absolute: they are the limits of the problem (``metadata.json``) times
the factors below.
"""

from pathlib import Path
from typing import NamedTuple

# Model and sampling. Every option is sent explicitly, so a default of the Modelfile or of an
# Ollama version never changes the experiment silently. The temperature and the seed of each
# attempt come from ATTEMPT_POLICY (below), never from here. MODEL is the model of the design (the
# 14B since 2026-10-06; it was the 7B); `OLLAMA_MODEL` in `.env` replaces it, for the pilots that
# compare models. The model in use is recorded in run.json, so a run never mixes two models.
MODEL = "qwen2.5-coder:14b"
TOP_P = 0.8
TOP_K = 20
REPEAT_PENALTY = 1.05

# Context window, from the largest assembled prompt of the 200 problems (8,074 characters with the
# template of 2026-10-04, hybrid scenario of 61_B); `num_ctx` counts prompt and answer together.
# The answer budget leaves 3,072 tokens for the prompt: the first pilot (2026-10-01) measured at
# least 3.32 characters per token, i.e. about 2,430 tokens for 61_B; a prompt that still does not
# fit stops the run (`prompt_eval_count + num_predict > num_ctx`), it is never truncated silently.
NUM_CTX = 8192
NUM_PREDICT = 5120


class AttemptSpec(NamedTuple):
    """One row of the attempt policy: what attempt ``attempt`` asks for, and how."""

    attempt: int
    phase: int  # 1 (seed varies), 2 (temperature falls) or 4 (prediction)
    seed: int
    temperature: float  # above 0: with greedy decoding the seed would have no effect
    template: str  # "solution" (slm_prompt.txt) or "prediction" (slm_predict_prompt.txt)


# The attempt policy of the experiment (the 5 phases of 2026-10-06), the ONLY source of the phase,
# seed, temperature and template of an attempt; written out row by row, recorded whole in run.json
# (a run never mixes two policies). Phases 1 and 2 stop at the first solution that passes every
# public test (`accepted`). Phase 3 makes no call: if none of the 12 passed, the best of them that
# failed a public test only by WA, and kept some generated input, is the suite (`accepted_fallback`;
# its expected outputs come from a solution known to be wrong on some input). Phase 4, only without
# a fallback, asks for a prediction (inputs AND expected outputs, no solution, nothing run); the
# first one parsed is the suite (`accepted_predicted`). Phase 5 makes no call either: without a
# parsed prediction the combination awaits the authors (`python -m ai_clients close`).
ATTEMPT_POLICY = (
    AttemptSpec(1, 1, 42, 0.7, "solution"),
    AttemptSpec(2, 1, 43, 0.7, "solution"),
    AttemptSpec(3, 1, 44, 0.7, "solution"),
    AttemptSpec(4, 1, 45, 0.7, "solution"),
    AttemptSpec(5, 1, 46, 0.7, "solution"),
    AttemptSpec(6, 1, 47, 0.7, "solution"),
    AttemptSpec(7, 2, 48, 0.7, "solution"),
    AttemptSpec(8, 2, 48, 0.6, "solution"),
    AttemptSpec(9, 2, 48, 0.5, "solution"),
    AttemptSpec(10, 2, 48, 0.4, "solution"),
    AttemptSpec(11, 2, 48, 0.3, "solution"),
    AttemptSpec(12, 2, 48, 0.2, "solution"),
    AttemptSpec(13, 4, 49, 0.7, "prediction"),
    AttemptSpec(14, 4, 50, 0.7, "prediction"),
    AttemptSpec(15, 4, 51, 0.7, "prediction"),
)
PHASE_TEMPLATE = {1: "solution", 2: "solution", 4: "prediction"}
FALLBACK_PHASE = 3  # the phase recorded for an accepted_fallback suite


def check_policy(policy: tuple[AttemptSpec, ...]) -> tuple[AttemptSpec, ...]:
    """``ValueError`` unless ``policy`` is a coherent table: 1..n without a gap, no (seed,
    temperature) pair twice, temperatures above 0, phases in order and with their template, and
    every solution attempt before every prediction."""
    if [spec.attempt for spec in policy] != list(range(1, len(policy) + 1)):
        raise ValueError("the attempts are numbered from 1 without a gap")
    pairs = [(spec.seed, spec.temperature) for spec in policy]
    if len(pairs) != len(set(pairs)):
        raise ValueError("a (seed, temperature) pair repeats: an attempt would repeat another")
    if any(spec.temperature <= 0 for spec in policy):
        raise ValueError("every temperature is above 0")
    phases = [spec.phase for spec in policy]
    if phases != sorted(phases) or any(spec.phase not in PHASE_TEMPLATE for spec in policy):
        raise ValueError("the phases are 1, 2 and 4, in this order")
    if any(spec.template != PHASE_TEMPLATE[spec.phase] for spec in policy):
        raise ValueError("phases 1 and 2 ask for a solution, phase 4 for a prediction")
    return policy


check_policy(ATTEMPT_POLICY)
SOLUTION_ATTEMPTS = sum(spec.template == "solution" for spec in ATTEMPT_POLICY)  # 12
MAX_ATTEMPTS = len(ATTEMPT_POLICY)  # 15

# Limits of the Python reference solution = limits of the problem times these factors.
PY_TIME_FACTOR = 10
PY_MEMORY_FACTOR = 4

# Waiting for Ollama. Both defaults can be overridden in `.env`; neither changes any answer, so
# neither is part of the identity of a run (`run.json`).
DEFAULT_HTTP_TIMEOUT_S = 900
DEFAULT_MAX_INFRA_RETRIES = 30
BACKOFF_START_S = 5
BACKOFF_MAX_S = 60  # the wait doubles after each consecutive failure, up to this value

# Canonical processing order of the three context scenarios.
SCENARIOS = ("black_box", "white_box", "hybrid")

# Environment variables (`.env`).
ENV_BASE_URL = "OLLAMA_BASE_URL"
ENV_HARDWARE_LABEL = "OLLAMA_HARDWARE_LABEL"
ENV_HTTP_TIMEOUT_S = "OLLAMA_HTTP_TIMEOUT_S"
ENV_MAX_INFRA_RETRIES = "OLLAMA_MAX_INFRA_RETRIES"
ENV_MODEL = "OLLAMA_MODEL"

# Layout under the repository root. Nothing under `data/suites/` is ever versioned; only the
# packaged result of the final run is.
DATA_DIR = Path("data")
DATASET_DIR = DATA_DIR / "dataset"
DATASET_PROBLEMS_DIR = DATASET_DIR / "problems"
SUITES_DIR = DATA_DIR / "suites" / "slm"
PROBLEMS_DIR = SUITES_DIR / "problems"
RUN_FILE = "run.json"
LOCK_FILE = ".lock"  # flock: shared by generate --resume/execute, exclusive otherwise (R24)
EXECUTE_LOCK_FILE = ".execute.lock"  # flock: one execute at a time (one engine slot)
COMBINATION_LOCKS_DIR = ".locks"  # flock per problem x scenario: <id>__<scenario>.lock
SUITE_FILE = "suite.json"
MANUAL_CLOSE_FILE = "manual_close.json"  # the decision of the authors (`close`)
# A template changed during the run (`change-template`, research R27): the record of each change,
# and the files it moved out of `problems/`, by change number.
TEMPLATE_CHANGES_DIR = "template_changes"  # <NNN>.json
SUPERSEDED_DIR = "superseded"  # <NNN>/<id>/<scenario>/<the moved files>


def template_change_file_name(number: int) -> str:
    """``<NNN>.json``: the number of the change with 3 digits."""
    return f"{number:03d}.json"


REPORT_PATH = Path("manifests") / "slm_generation_report.json"
MANIFEST_PATH = Path("manifests") / "slm_suites.manifest.json"
DATASET_MANIFEST_PATH = Path("manifests") / "dataset.manifest.json"
ZIP_PATH = DATA_DIR / "slm_suites.zip"
ZIP_ROOT = "suites/slm"  # `unzip data/slm_suites.zip -d data/` lands on SUITES_DIR

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompt_templates" / "slm_prompt.txt"
PREDICT_TEMPLATE_PATH = PROMPT_TEMPLATE_PATH.with_name("slm_predict_prompt.txt")
TEMPLATE_FILES = {"solution": PROMPT_TEMPLATE_PATH.name, "prediction": PREDICT_TEMPLATE_PATH.name}


def attempt_spec(attempt: int) -> AttemptSpec:
    """The row of ``attempt`` (1 to MAX_ATTEMPTS) in ATTEMPT_POLICY."""
    if not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError(f"attempt must be in [1, {MAX_ATTEMPTS}], got {attempt}")
    return ATTEMPT_POLICY[attempt - 1]


def attempt_kind(attempt: int) -> str:
    """``solution`` or ``prediction``: the template of ``attempt``."""
    return attempt_spec(attempt).template


def generation_file_name(attempt: int) -> str:
    """``attempt_<n>.generation.json``."""
    return f"attempt_{attempt}.generation.json"


def execution_file_name(attempt: int) -> str:
    """``attempt_<n>.execution.json``."""
    return f"attempt_{attempt}.execution.json"
