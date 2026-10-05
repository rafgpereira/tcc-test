"""Two full runs give the same selection and byte-identical files (T075; FR-025, SC-007).

`test_wa.py` already proves, at the `collect_wa` level, that the retained set does not depend on
worker speed (results are consumed in candidate order, not completion order). This file proves the
same thing end to end, through `run_validate`, and adds the two invariants that are only visible
at that level: two full runs on the same input produce byte-identical `problems/` trees (aside
from `extraction_timestamp`, which is a wall-clock fact, not a selection outcome), and the seeded
streams `dataset.config.seeded_random` hands out do not depend on `PYTHONHASHSEED` (`random.seed`
hashes a string seed with SHA-512, not with the interpreter's randomized `hash()`; this pins that
fact, so a future change that broke it would be caught here instead of only showing up as an
unreproducible dataset run).
"""

import json

import pytest

from dataset import config
from dataset.filtering.classification import classify
from dataset.persistence import store
from dataset.schemas.pool import Pool, PoolCounts, PoolProblem
from dataset.validation import pipeline
from dataset.validation.runtime import InlineRuntime, ThreadRuntime
from tests.dataset.validation.conftest import FakeEngine


def wa_sources(n=140, tag=""):
    # mostly WA, with some CE mixed in so the candidate walk exercises more than one outcome;
    # 4 of every 5 are WA, comfortably above the 100 needed after the walk and any discards
    kinds = ["WA@0", "WA@1", "WA@2", "WA@0", "CE"]
    return [f"// {kinds[i % len(kinds)]}\nint main(){{return {i};}} {tag}" for i in range(n)]


def build_pool_and_raw(root, raws):
    problems = {
        raw.problem_id: PoolProblem(
            split=raw.split,
            shard_index=0,
            macrocategoria=classify(raw.cf_tags),
            raw_wa_count=len(raw.incorrect_solutions),
            raw_ac_count=len(raw.correct_solutions),
            source_row=i,
        )
        for i, raw in enumerate(raws)
    }
    pool = Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=42,
        counts=PoolCounts(funnel={"read": len(raws)}, rejections={}, eligible=len(raws)),
        order=[raw.problem_id for raw in raws],
        problems=problems,
    )
    store.atomic_write_json(root / config.STAGING_DIR / "pool.json", pool)
    for raw in raws:
        store.atomic_write_json_gz(root / config.RAW_DIR / f"{raw.problem_id}.json.gz", raw)


def selfcheck_ok():
    from sandbox.selfcheck import CaseResult, SelfCheckReport
    from sandbox.types import Verdict

    case = CaseResult("ac", Verdict.AC, Verdict.AC, "gnu++20", True, True)
    return SelfCheckReport(ok=True, cases=(case,))


def run_full(tmp_path_factory, runtime_factory, raws):
    root = tmp_path_factory.mktemp("run")
    store.ensure_work_dir(root)
    build_pool_and_raw(root, raws)
    pipeline.run_validate(
        root,
        target=len(raws),
        workers=1,  # `runtime_factory` decides the real concurrency, not this
        problem=None,
        runtime_factory=runtime_factory,
        selfcheck_fn=selfcheck_ok,
        out=lambda line: None,
    )
    return root


def problems_without_timestamp(root):
    """``{problem_id: {relative path: bytes}}``, with ``extraction_timestamp`` blanked out."""
    result = {}
    for folder in sorted((root / config.PROBLEMS_DIR).iterdir()):
        files = {}
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if path.name == "metadata.json":
                obj = json.loads(data)
                obj["extraction_timestamp"] = "REDACTED"
                data = json.dumps(obj, sort_keys=True).encode()
            files[str(path.relative_to(folder))] = data
        result[folder.name] = files
    return result


def test_two_full_runs_produce_byte_identical_trees_except_the_timestamp(
    tmp_path_factory, make_raw
):
    raws = [make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2, 3)]

    def factory(workers):
        return InlineRuntime(FakeEngine().as_engine())

    root_a = run_full(tmp_path_factory, factory, raws)
    root_b = run_full(tmp_path_factory, factory, raws)
    assert problems_without_timestamp(root_a) == problems_without_timestamp(root_b)
    # the timestamp itself is the only thing allowed to differ (both are still well-formed)
    ts_a = json.loads((root_a / config.PROBLEMS_DIR / "1_A" / "metadata.json").read_text())
    ts_b = json.loads((root_b / config.PROBLEMS_DIR / "1_A" / "metadata.json").read_text())
    assert "extraction_timestamp" in ts_a and "extraction_timestamp" in ts_b


def test_the_retained_wa_set_is_identical_with_one_worker_and_with_many(tmp_path_factory, make_raw):
    """`InlineRuntime` (window 1) against `ThreadRuntime` (window 16, staggered per-candidate
    delays so real completion order differs from submission order): both must retain the exact
    same 100 WA, because `collect_wa` consumes results in candidate order, never completion order
    (FR-025)."""
    raws = [make_raw("1_A", wa=wa_sources())]
    sources = raws[0].incorrect_solutions
    # every other candidate is slow: under real thread concurrency, later ones finish first
    delay = {item.source: (0.01 if i % 2 == 0 else 0.0) for i, item in enumerate(sources)}

    root_1 = run_full(
        tmp_path_factory, lambda workers: InlineRuntime(FakeEngine().as_engine()), raws
    )
    root_n = run_full(
        tmp_path_factory, lambda workers: ThreadRuntime(FakeEngine(delay).as_engine(), 8), raws
    )
    assert problems_without_timestamp(root_1) == problems_without_timestamp(root_n)


@pytest.mark.parametrize("context", ["pool", "wa:1101_A", "wa:99_Z"])
def test_seeded_random_does_not_depend_on_pythonhashseed(context):
    """`random.seed(str)` hashes with SHA-512 (see CPython `Random.seed`), not `hash()`: the
    sequence must be the same across processes regardless of `PYTHONHASHSEED`. Run in a
    subprocess with hash randomization forced on (the default) and off, and compare."""
    import subprocess
    import sys

    code = f"import random\nrandom.seed('42:{context}')\nprint(random.random())\n"
    first = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONHASHSEED": "0"},
        check=True,
    ).stdout.strip()
    second = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONHASHSEED": "random"},
        check=True,
    ).stdout.strip()
    assert first == second
