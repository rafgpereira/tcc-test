"""Resume after an interruption never touches closed problems (T074; FR-023, FR-024).

`test_pipeline.py` already covers most of the resume mechanics (a partial `building/` is
discarded and rebuilt, an already-closed problem is skipped and not recompiled, `reset_building`
runs once per `validate` invocation). This file adds the invariants the spec calls out that
those tests do not check directly: closed problems are not just "not recompiled" but their files
on disk are never even opened for writing again (same bytes, same mtime); `pending_triage` and
`discarded` problems are just as untouched as `complete` ones; and a second run of an already
finished execution is a true no-op.
"""

import json

import pytest

from dataset import config
from dataset.persistence import store
from dataset.validation import pipeline
from dataset.validation.runtime import InlineRuntime


def wa_sources(n=120, mark="WA@0", tag=""):
    return [f"// {mark}\nint main(){{return {i};}} {tag}" for i in range(n)]


@pytest.fixture()
def root(tmp_path):
    store.ensure_work_dir(tmp_path)
    return tmp_path


@pytest.fixture()
def prepare(root):
    from dataset.filtering.classification import classify
    from dataset.schemas.pool import Pool, PoolCounts, PoolProblem

    def _prepare(raws):
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

    return _prepare


def selfcheck_ok():
    from sandbox.selfcheck import CaseResult, SelfCheckReport
    from sandbox.types import Verdict

    case = CaseResult("ac", Verdict.AC, Verdict.AC, "gnu++20", True, True)
    return SelfCheckReport(ok=True, cases=(case,))


@pytest.fixture()
def factory(fake):
    def _factory(workers):
        return InlineRuntime(fake.as_engine())

    return _factory


def run(root, factory, *, target, workers=2, problem=None):
    lines = []
    code = pipeline.run_validate(
        root,
        target=target,
        workers=workers,
        problem=problem,
        runtime_factory=factory,
        selfcheck_fn=selfcheck_ok,
        out=lines.append,
    )
    return code, lines


def snapshot(folder):
    """``{relative path: (bytes, mtime_ns)}`` for every file under ``folder``, recursively."""
    return {
        str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_a_complete_problem_is_byte_identical_and_untouched_on_resume(
    root, prepare, factory, make_raw
):
    prepare(
        [
            make_raw("1_A", wa=wa_sources()),
            make_raw("2_A", wa=wa_sources(tag="2")),
        ]
    )
    run(root, factory, target=1)
    before = snapshot(root / config.PROBLEMS_DIR / "1_A")
    assert before  # sanity: the folder really has files

    run(root, factory, target=2)  # resume: must reach the second problem without touching the first
    after = snapshot(root / config.PROBLEMS_DIR / "1_A")
    assert after == before  # same bytes AND same mtime: the file was never reopened for writing
    assert (root / config.PROBLEMS_DIR / "2_A" / "validacao.json").is_file()


def test_pending_triage_and_discarded_problems_are_not_reprocessed_on_resume(
    root, prepare, factory, make_raw
):
    prepare(
        [
            make_raw("1_A", ac=("// WA@0\nx",), wa=wa_sources()),  # -> pending_triage
            make_raw("2_A", wa=wa_sources(60) * 2),  # only 60 distinct texts -> discarded
            make_raw("3_A", wa=wa_sources(tag="3")),
        ]
    )
    run(root, factory, target=1)
    statuses = {
        p.name: json.loads((p / "validacao.json").read_text())["status"]
        for p in (root / config.PROBLEMS_DIR).iterdir()
    }
    assert statuses == {"1_A": "pending_triage", "2_A": "discarded", "3_A": "complete"}
    before_triage = snapshot(root / config.PROBLEMS_DIR / "1_A")
    before_discarded = snapshot(root / config.PROBLEMS_DIR / "2_A")

    code, lines = run(root, factory, target=5)  # nothing left in the pool: pure resume attempt
    assert code == 1  # deficit: the pool is exhausted, D17 says they now need inspection
    assert any("1_A" in line and "already closed" in line for line in lines)
    assert any("2_A" in line and "already closed" in line for line in lines)
    assert snapshot(root / config.PROBLEMS_DIR / "1_A") == before_triage
    assert snapshot(root / config.PROBLEMS_DIR / "2_A") == before_discarded


def test_rerunning_a_finished_execution_changes_nothing_and_adds_nothing_beyond_target(
    root, prepare, factory, make_raw
):
    raws = [make_raw(f"{i}_A", wa=wa_sources(tag=str(i))) for i in (1, 2)]
    prepare(raws)
    code, _ = run(root, factory, target=2)
    assert code == 0
    before = {p.name: snapshot(p) for p in (root / config.PROBLEMS_DIR).iterdir()}

    code, _ = run(root, factory, target=2)  # already done: must be a pure no-op
    assert code == 0
    after = {p.name: snapshot(p) for p in (root / config.PROBLEMS_DIR).iterdir()}
    assert after == before
    assert set(after) == {"1_A", "2_A"}  # no problem added beyond the target
