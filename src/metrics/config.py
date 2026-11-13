"""Fixed configuration of the metrics module (docs/metodologia-referencia.md, section 5)."""

from pathlib import Path

SETS = ("slm", "gpt", "gemini", "claude", "slm-attempt1")
MODELS = ("slm", "gpt", "gemini", "claude")  # the official comparison of the models
COMMERCIAL = ("gpt", "gemini", "claude")
SCENARIOS = ("black_box", "white_box", "hybrid")
SET_MODEL = {"slm": "slm", "gpt": "gpt", "gemini": "gemini", "claude": "claude"}
SET_MODEL["slm-attempt1"] = "slm"

ALPHA = 0.05
WA_PER_PROBLEM = 100
MUTANTS_PER_PROBLEM = 100
DECIMALS = 4

EVALUATION_DIR = Path("data/evaluation")
METRICS_DIR = Path("data/metrics")
FIGURES_DIR = METRICS_DIR / "figures"
DATASET_PROBLEMS_DIR = Path("data/dataset/problems")
DATASET_MANIFEST = Path("manifests/dataset.manifest.json")
METRICS_ZIP = Path("data/metrics.zip")
METRICS_MANIFEST = Path("manifests/metrics.manifest.json")

TABLES = {
    "per_problem": "per_problem.csv",
    "detected_wa": "detected_wa.csv",
    "metrics": "metrics.csv",
    "iic": "iic.csv",
    "stats": "stats.csv",
    "cost": "cost.csv",
}
RUN_FILE = "run.json"


def evaluation_manifest(set_name: str) -> Path:
    return Path("manifests") / f"evaluation_{set_name}.manifest.json"


def evaluation_report(set_name: str) -> Path:
    return Path("manifests") / f"evaluation_{set_name}_report.json"


def generation_report(model: str) -> Path:
    return Path("manifests") / f"{model}_generation_report.json"


PACKAGED_FIGURE_FORMATS = (
    "png",
    "svg",
)  # the figure formats that are the same bytes on every call (no figure is packaged since 2026-11-13)
