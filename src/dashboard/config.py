"""Fixed configuration of the dashboard (read only: nothing here is ever written)."""

from pathlib import Path

DEFAULT_EVALUATION_DIR = Path("data/evaluation")
METRICS_DIR = Path("data/metrics")  # where the metrics module will write its tables
PORT = 8501
SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")
SCENARIOS = ("black_box", "white_box", "hybrid")
PREVIEW_LABEL = "prévia"

# `serve` passes the folder to the Streamlit script through this variable.
ENV_EVALUATION_DIR = "DASHBOARD_EVALUATION_DIR"
