"""Valid records of the commercial models, as dicts, for the schema and state tests."""

from ai_clients.llm import config
from ai_clients.llm.providers import request_parameters
from ai_clients.llm.schemas import price_table, response_schema

SHA = "a" * 64
OTHER_SHA = "b" * 64


def price_row(model="gpt") -> dict:
    return next(r for r in price_table() if r.model_key == model).model_dump(mode="json")


def run_config(model="gpt", **changes) -> dict:
    data = {
        "schema_version": 1,
        "model_key": model,
        "model_requested": config.MODEL_ID[model],
        "endpoint": config.ENDPOINT[model],
        "request_parameters": request_parameters(model),
        "response_schema": response_schema(),
        "template_sha256": SHA,
        "max_attempts": 3,
        "dataset_manifest_sha256": OTHER_SHA,
        "price_table": [r.model_dump(mode="json") for r in price_table()],
        "created_at": "2026-10-20T12:00:00Z",
    }
    data.update(changes)
    return data


def parsed(tests=(("1\n", "1\n"),), **counters) -> dict:
    data = {
        "ok": True,
        "edge_cases_analysis": "n = 1 is the smallest case.\n",
        "tests": [{"input": i, "output": o} for i, o in tests],
        "empty_tests": 0,
        "abbreviated_tests": 0,
        "markdown_fences_removed": 0,
        "duplicate_inputs": 0,
        "conflicting_outputs": 0,
        "example_copies": 0,
    }
    data.update(counters)
    return data


def failed(failure="not_json", detail="Expecting value") -> dict:
    return {"ok": False, "failure": failure, "detail": detail}


def call_record(model="gpt", problem_id="1_A", scenario="black_box", **changes) -> dict:
    data = {
        "schema_version": 1,
        "problem_id": problem_id,
        "scenario": scenario,
        "model_requested": config.MODEL_ID[model],
        "model_returned": config.MODEL_ID[model],
        "response_id": "resp_1",
        "prompt_sha256": SHA,
        "template_sha256": SHA,
        "request_parameters": request_parameters(model),
        "requested_at": "2026-10-20T12:00:00Z",
        "latency_s": 2.5,
        "http_status": 200,
        "raw_body": "{}",
        "finish": {"status": "completed", "reason": None, "safety_categories": []},
        "usage": {
            "input_tokens": 2000,
            "cached_input_tokens": 0,
            "output_tokens": 1500,
            "reasoning_tokens": 1200,
        },
        "cost_usd": 0.00825,
        "price_row": price_row(model),
    }
    data.update(changes)
    return data


def attempt(n=1, parse=None, **changes) -> dict:
    data = call_record(**changes)
    data.update(attempt=n, parse=parse if parse is not None else parsed())
    return data


def summary(n=1, failure=None, detail="1 kept", model_returned="gpt-5.4-mini-2026-03-17") -> dict:
    return {
        "attempt": n,
        "failure": failure,
        "detail": detail,
        "model_returned": model_returned,
        "cost_usd": 0.01,
    }


def llm_suite(status="accepted_predicted", **changes) -> dict:
    if status == "accepted_predicted":
        data = {
            "model_digest": "gpt-5.4-mini-2026-03-17",
            "attempts": [summary(1)],
            "accepted_attempt": 1,
            "tests": [{"input": "1\n", "output": "1\n"}],
            "suite_size": 1,
            "manual_close": None,
        }
    else:
        data = {
            "model_digest": None,
            "attempts": [summary(n, failure="not_json", detail="x") for n in (1, 2, 3)],
            "accepted_attempt": None,
            "tests": [],
            "suite_size": 0,
            "manual_close": {"reason": "never parsed", "closed_at": "2026-10-21T00:00:00Z"},
        }
    data.update(
        schema_version=2,
        problem_id="1_A",
        scenario="black_box",
        model="gpt-5.4-mini-2026-03-17",
        status=status,
        accepted_phase=None,
        discarded_inputs=[],
        duplicate_inputs=0,
    )
    data.update(changes)
    return data
