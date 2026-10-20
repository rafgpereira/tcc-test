"""Fixed configuration of the commercial models (docs/metodologia-referencia.md, section 3).

Every constant here is part of the experiment design (specs/004-llm-test-generation/research.md,
A3 and R0-R14). The operator sets only the API keys and, optionally, how many calls run together,
how many consecutive infrastructure failures to tolerate and how long to wait for an answer; they
come from ``.env`` (names below), never from this file, and none of them changes an answer.

No sampling parameter is ever sent (no seed, no temperature, no top_p/top_k): the provenance of an
answer is the model version returned by the API, the parameters sent and the raw answer (A3).
"""

from datetime import date
from pathlib import Path
from typing import NamedTuple

from ai_clients import config as slm_config

MODELS = ("gpt", "gemini", "claude")  # the key used by the command line and by the folders

MODEL_ID = {
    "gpt": "gpt-5.4-mini-2026-03-17",
    "gemini": "gemini-3.8-flash",
    "claude": "claude-haiku-5-5",
}
ENDPOINT = {
    "gpt": "https://api.openai.com/v1/responses",
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    ),
    "claude": "https://api.anthropic.com/v1/messages",
}
# The version of the Messages API (header anthropic-version; specs/008, research R1).
ANTHROPIC_VERSION = "2023-06-01"

# Reasoning effort, sent explicitly to the three (the default of gpt-5.4-mini is "none"; Claude
# Haiku 5.5 takes it as output_config.effort, with adaptive thinking).
REASONING_LEVEL = "medium"
# Output ceiling (answer + reasoning), the same for the three (R12; specs/008, clarify).
MAX_OUTPUT_TOKENS = 32768
# New calls of one problem x scenario, only after a format failure (A1).
MAX_ATTEMPTS = 3

# Waiting. Defaults overridable in `.env`; none of them is part of the identity of a run.
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_MAX_INFRA_RETRIES = 30
DEFAULT_HTTP_TIMEOUT_S = 900
BACKOFF_START_S = slm_config.BACKOFF_START_S
BACKOFF_MAX_S = slm_config.BACKOFF_MAX_S

# Characters per input token, to estimate the cost without calling anything (R9). 3.0 is
# conservative (the SLM measured at least 3.32): conservative, before the pilot.
# Gemini: measured in its pilot 1 (2026-10-16, 15 calls): 69,717 prompt characters for 20,786
# input tokens reported by the API.
CHARS_PER_TOKEN = {"gpt": 3.0, "gemini": 3.354, "claude": 3.0}
CHARS_PER_TOKEN_ORIGIN = {
    "gpt": "conservative, before the pilot",
    "gemini": "measured in pilot 1, 2026-10-16",
    "claude": "conservative, before the pilot",
}
# Mean output tokens per call (answer + reasoning) measured in the pilot (None before it): the
# low end of the estimate. Gemini, pilot 1 (2026-10-16): 1,965 (median 1,640, max 3,551).
MEASURED_MEAN_OUTPUT_TOKENS: dict[str, int | None] = {"gpt": None, "gemini": 1965, "claude": None}


class Price(NamedTuple):
    """One row of the price table, in US$ per million tokens (research R9)."""

    model_key: str
    valid_from: date
    input_per_mtok: float
    cached_input_per_mtok: float
    output_per_mtok: float
    source: str
    accessed_on: date


_OPENAI_SOURCE = "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
_GEMINI_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
_CLAUDE_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
_ACCESSED = date(2026, 10, 15)
_CLAUDE_ACCESSED = date(2026, 10, 20)

PRICE_TABLE = (
    Price("gpt", date(2026, 10, 15), 0.75, 0.075, 4.50, _OPENAI_SOURCE, _ACCESSED),
    Price("gemini", date(2026, 10, 15), 0.75, 0.075, 3.75, _GEMINI_SOURCE, _ACCESSED),
    Price("gemini", date(2027, 1, 1), 1.50, 0.15, 7.50, _GEMINI_SOURCE, _ACCESSED),
    # Prompts up to CLAUDE_PROMPT_TOKEN_LIMIT tokens; a longer prompt has another price.
    Price("claude", date(2026, 10, 20), 0.10, 0.01, 0.50, _CLAUDE_SOURCE, _CLAUDE_ACCESSED),
)
# Claude Haiku 5.5 is priced by prompt length (specs/008, research R4): above this many input
# tokens the price row above does not apply, and the call is refused before it is sent.
CLAUDE_PROMPT_TOKEN_LIMIT = 100_000

# Environment variables (`.env`).
ENV_API_KEY = {
    "gpt": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}
ENV_MAX_CONCURRENCY = {
    "gpt": "OPENAI_MAX_CONCURRENCY",
    "gemini": "GEMINI_MAX_CONCURRENCY",
    "claude": "ANTHROPIC_MAX_CONCURRENCY",
}
ENV_MAX_INFRA_RETRIES = {
    "gpt": "OPENAI_MAX_INFRA_RETRIES",
    "gemini": "GEMINI_MAX_INFRA_RETRIES",
    "claude": "ANTHROPIC_MAX_INFRA_RETRIES",
}
# Optional: at most this many request starts per minute (retries included); unset = no pacing.
ENV_MAX_REQUESTS_PER_MINUTE = {
    "gpt": "OPENAI_MAX_REQUESTS_PER_MINUTE",
    "gemini": "GEMINI_MAX_REQUESTS_PER_MINUTE",
    "claude": "ANTHROPIC_MAX_REQUESTS_PER_MINUTE",
}
ENV_HTTP_TIMEOUT_S = "LLM_HTTP_TIMEOUT_S"

# Layout under the repository root; one tree per model.
SCENARIOS = slm_config.SCENARIOS
RUN_FILE = slm_config.RUN_FILE
SUITE_FILE = slm_config.SUITE_FILE
MANUAL_CLOSE_FILE = slm_config.MANUAL_CLOSE_FILE
TEMPLATE_CHANGES_DIR = slm_config.TEMPLATE_CHANGES_DIR
SUPERSEDED_DIR = slm_config.SUPERSEDED_DIR
BARRED_DIR = "barred"  # answers without reasoning tokens, kept out of the attempts (FR-018a)
# After this many answers without reasoning, the combination takes the last one that can be
# read (accepted_barred) instead of asking again (FR-018a, amended on 2026-10-20).
MAX_BARRED = 3
LLM_TEMPLATE_PATH = slm_config.PROMPT_TEMPLATE_PATH.with_name("llm_prompt.txt")
TEMPLATE_KIND = "llm"


def check_model(model: str) -> str:
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; expected one of {', '.join(MODELS)}")
    return model


def suites_dir(model: str) -> Path:
    return slm_config.DATA_DIR / "suites" / check_model(model)


def problems_dir(model: str) -> Path:
    return suites_dir(model) / "problems"


def report_path(model: str) -> Path:
    return Path("manifests") / f"{check_model(model)}_generation_report.json"


def manifest_path(model: str) -> Path:
    return Path("manifests") / f"{check_model(model)}_suites.manifest.json"


def zip_path(model: str) -> Path:
    return slm_config.DATA_DIR / f"{check_model(model)}_suites.zip"


def zip_root(model: str) -> str:
    return f"suites/{check_model(model)}"


def attempt_file_name(attempt: int) -> str:
    """``attempt_<n>.json``, 1 <= n <= 3."""
    if not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError(f"attempt must be in [1, {MAX_ATTEMPTS}], got {attempt}")
    return f"attempt_{attempt}.json"
