"""The common reader reads every ``suite.json`` of the three models alike (SC-007).

The SLM suites are built with ``SlmSuite`` (each status, with the rows of its attempt policy), the
commercial ones with ``LlmSuite``; ``read_suite_view`` reads both without knowing the model, while
each validator keeps refusing the other module's suites.
"""

import json

import pytest
from pydantic import ValidationError

from ai_clients import config
from ai_clients.llm.schemas import LlmSuite
from ai_clients.schemas.suite import SlmSuite
from ai_clients.schemas.suite_view import read_suite_view
from tests.ai_clients.llm import builders as b


def slm_summary(n, failure="public_test_failed", fallback=False):
    spec = config.attempt_spec(n)
    return {
        "attempt": n,
        "phase": spec.phase,
        "seed": spec.seed,
        "temperature": spec.temperature,
        "template": spec.template,
        "hardware_label": "RTX 3060 12GB",
        "failure": failure,
        "detail": "x",
        "fallback_eligible": fallback,
    }


def slm_suite(status) -> dict:
    tests = [{"input": "1\n", "output": "1\n"}]
    base = {
        "schema_version": 2,
        "problem_id": "1_A",
        "scenario": "black_box",
        "model": "qwen2.5-coder:14b",
        "model_digest": "sha256:abc",
        "status": status,
        "tests": tests,
        "suite_size": 1,
        "discarded_inputs": [],
        "duplicate_inputs": 0,
        "manual_close": None,
    }
    if status == "accepted":
        return base | {
            "accepted_phase": 1,
            "attempts": [slm_summary(1, None)],
            "accepted_attempt": 1,
        }
    if status == "accepted_fallback":
        attempts = [slm_summary(n, fallback=(n == 3)) for n in range(1, 13)]
        return base | {"accepted_phase": 3, "attempts": attempts, "accepted_attempt": 3}
    if status == "accepted_predicted":
        attempts = [slm_summary(n, "unparseable_response") for n in range(1, 13)]
        attempts.append(slm_summary(13, None))
        return base | {"accepted_phase": 4, "attempts": attempts, "accepted_attempt": 13}
    attempts = [slm_summary(n, "unparseable_response") for n in range(1, 16)]
    return base | {
        "accepted_phase": None,
        "attempts": attempts,
        "accepted_attempt": None,
        "tests": [],
        "suite_size": 0,
        "manual_close": {"reason": "never parsed", "closed_at": "2026-10-08"},
    }


SLM = ["accepted", "accepted_fallback", "accepted_predicted", "discarded_manual"]
LLM = ["accepted_predicted", "discarded_manual"]


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("status", SLM)
def test_every_slm_suite_is_read(tmp_path, status):
    data = SlmSuite.model_validate(slm_suite(status)).model_dump(mode="json")
    view = read_suite_view(write(tmp_path, "s.json", data))
    assert (view.model, view.status.value, view.suite_size) == (
        "qwen2.5-coder:14b",
        status,
        len(data["tests"]),
    )


@pytest.mark.parametrize("status", LLM)
def test_every_llm_suite_is_read(tmp_path, status):
    data = LlmSuite.model_validate(b.llm_suite(status)).model_dump(mode="json")
    view = read_suite_view(write(tmp_path, "s.json", data))
    assert (view.model, view.status.value) == ("gpt-5.4-mini-2026-03-17", status)
    assert [t.model_dump() for t in view.tests] == data["tests"]


def test_an_incoherent_suite_is_refused(tmp_path):
    with pytest.raises(ValidationError):
        read_suite_view(write(tmp_path, "a.json", b.llm_suite(suite_size=2)))
    with pytest.raises(ValidationError):
        read_suite_view(write(tmp_path, "b.json", b.llm_suite(tests=[], suite_size=0)))


def test_each_validator_still_refuses_the_other_module():
    with pytest.raises(ValidationError):
        SlmSuite.model_validate(b.llm_suite())
    with pytest.raises(ValidationError):
        LlmSuite.model_validate(slm_suite("accepted_predicted"))
