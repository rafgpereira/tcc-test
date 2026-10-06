"""Fixed configuration of the SLM test-suite generation (docs/metodologia-referencia.md, section 3).

Every constant here is part of the experiment design. The only values the operator sets are the
address of the Ollama server, the hardware label and, optionally, how long to wait for an answer,
how many consecutive infrastructure failures to tolerate and another model for a pilot; they come
from ``.env`` (names below), never from this file. The time and memory limits of the Python reference solution are
NEVER absolute: they are the limits of the problem (``metadata.json``) times the factors below.
"""

from pathlib import Path

# Model and sampling. Every option is sent explicitly, so a default of the Modelfile or of an
# Ollama version never changes the experiment silently. `temperature` must stay above 0: with
# greedy decoding the seed has no effect and the attempts would repeat the same answer.
# MODEL is the model of the design; `OLLAMA_MODEL` in `.env` replaces it, for the pilots that
# compare models. The model in use is recorded in run.json, so a run never mixes two models.
MODEL = "qwen2.5-coder:7b"
TEMPERATURE = 0.7
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

# Attempts: attempt n (1..MAX_ATTEMPTS) uses the seed SEED_BASE + n, i.e. 43..65; no problem ×
# scenario ends without a suite. In the first STRICT_ATTEMPTS only an attempt whose solution
# passes every public test is accepted. If none of them is, the best of them whose solution failed
# a public test only by WA, and kept some generated input, is accepted as a fallback (status
# `accepted_fallback`: its expected outputs come from a solution known to be wrong on some input).
# If none of the 8 can be a fallback either, attempts 9..SOLUTION_ATTEMPTS accept the first one
# that passes or can be a fallback. After the 20th without either, the first of the 20 whose
# solution kept some generated input is accepted with low confidence (`accepted_low_confidence`:
# it failed a public test by RE, TLE or MLE). Without one, attempts SOLUTION_ATTEMPTS+1..
# MAX_ATTEMPTS ask for a prediction (the second template: inputs AND expected outputs, no
# solution, nothing run) and the first one parsed is the suite (`accepted_predicted`). If none of
# them is parsed, the combination awaits manual handling: the authors close it with
# `python -m ai_clients close` (`discarded_manual`).
SEED_BASE = 42
STRICT_ATTEMPTS = 8
SOLUTION_ATTEMPTS = 20
PREDICT_ATTEMPTS = 3
MAX_ATTEMPTS = SOLUTION_ATTEMPTS + PREDICT_ATTEMPTS

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
LOCK_FILE = ".lock"  # flock: one command at a time over data/suites/slm/
SUITE_FILE = "suite.json"
MANUAL_CLOSE_FILE = "manual_close.json"  # the decision of the authors (`close`)

REPORT_PATH = Path("manifests") / "slm_generation_report.json"
MANIFEST_PATH = Path("manifests") / "slm_suites.manifest.json"
DATASET_MANIFEST_PATH = Path("manifests") / "dataset.manifest.json"
ZIP_PATH = DATA_DIR / "slm_suites.zip"
ZIP_ROOT = "suites/slm"  # `unzip data/slm_suites.zip -d data/` lands on SUITES_DIR

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "prompt_templates" / "slm_prompt.txt"
PREDICT_TEMPLATE_PATH = PROMPT_TEMPLATE_PATH.with_name("slm_predict_prompt.txt")


def attempt_kind(attempt: int) -> str:
    """``solution`` for attempts 1..SOLUTION_ATTEMPTS, ``prediction`` for the last ones."""
    if not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError(f"attempt must be in [1, {MAX_ATTEMPTS}], got {attempt}")
    return "solution" if attempt <= SOLUTION_ATTEMPTS else "prediction"


def seed_for(attempt: int) -> int:
    """The seed of attempt ``attempt`` (1 to MAX_ATTEMPTS): ``SEED_BASE + attempt``."""
    if not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError(f"attempt must be in [1, {MAX_ATTEMPTS}], got {attempt}")
    return SEED_BASE + attempt


def generation_file_name(attempt: int) -> str:
    """``attempt_<n>.generation.json``."""
    return f"attempt_{attempt}.generation.json"


def execution_file_name(attempt: int) -> str:
    """``attempt_<n>.execution.json``."""
    return f"attempt_{attempt}.execution.json"
