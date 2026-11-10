"""Fixed configuration of the dashboard (read only: nothing here is ever written)."""

from pathlib import Path

DEFAULT_EVALUATION_DIR = Path("data/evaluation")
METRICS_DIR = Path("data/metrics")  # where the metrics module will write its tables
PORT = 8501
SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")
SCENARIOS = ("black_box", "white_box", "hybrid")
PREVIEW_LABEL = "prévia"

# What the public copy (Streamlit Community Cloud) reads: the versioned packages, unzipped into
# data/ on its first start (evaluation, metrics, dataset, mutants and the suites of each model; the
# first attempt of the SLM is inside the SLM suites).
PUBLIC_PACKAGES = (
    "data/evaluation_slm.zip",
    "data/evaluation_gpt.zip",
    "data/evaluation_gemini.zip",
    "data/evaluation_claude.zip",
    "data/evaluation_slm-attempt1.zip",
    "data/metrics.zip",
    "data/dataset.zip",
    "data/mutants.zip",
    "data/slm_suites.zip",
    "data/gpt_suites.zip",
    "data/gemini_suites.zip",
    "data/claude_suites.zip",
)

# `serve` passes the folder to the Streamlit script through this variable.
ENV_EVALUATION_DIR = "DASHBOARD_EVALUATION_DIR"
