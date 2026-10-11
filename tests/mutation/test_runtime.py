"""Tests for the runtimes of `generate`: the number of workers never changes the result (R14).

The fake engine answers from the content of each candidate; a delay that depends on the problem
makes the problems finish in the reverse order of submission when they run in threads.
"""

import time
from pathlib import Path

import pytest

import mutation.__main__ as cli
from mutation import config, runtime
from mutation.runtime import ProblemTask
from sandbox.types import InfraError, Verdict


def tree_of(root: Path) -> dict[str, bytes]:
    """Every file under `data/mutants/problems`, by relative path."""
    base = root / config.PROBLEMS_DIR
    return {
        p.relative_to(base).as_posix(): p.read_bytes()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


@pytest.fixture()
def four_problems(tmp_path, dataset_builder, dense_problem):
    def renamed(pid):
        return {
            name: text.replace('"problem_id": "189_C"', f'"problem_id": "{pid}"')
            for name, text in dense_problem.items()
        }

    ids = ["189_C", "189_D", "189_E", "189_F"]
    dataset_builder(tmp_path, {pid: renamed(pid) for pid in ids})
    return tmp_path, ids


def run_generate(root, ids, rt):
    return cli.generate(root, ids, rt, lambda message: None)


def test_threads_that_finish_in_reverse_order_write_the_same_bytes_as_one_worker(
    four_problems, make_engine, tmp_path_factory
):
    root, ids = four_problems
    engine = make_engine(lambda source: ["CE"] if hash_mod(source) == 0 else [Verdict.WA])

    class Slow(runtime.ThreadRuntime):
        """The first problems take the longest, so the last one finishes first."""

        def _run(self, task: ProblemTask):
            time.sleep(0.05 * (len(ids) - ids.index(task.problem_id)))
            return super()._run(task)

    parallel = run_generate(root, ids, Slow(engine.as_engine(), workers=4))
    assert sorted(parallel.generated) == ids
    parallel_tree = tree_of(root)

    import shutil

    shutil.rmtree(root / config.MUTANTS_DIR)
    serial = run_generate(root, ids, runtime.InlineRuntime(make_engine(engine.script).as_engine()))
    assert sorted(serial.generated) == ids
    assert tree_of(root) == parallel_tree
    assert len(parallel_tree) == 4 * 101


def hash_mod(source: str) -> int:
    from mutation.validation import sha256_of

    return int(sha256_of(source), 16) % 5


def test_an_infrastructure_failure_in_a_worker_propagates_and_writes_nothing_for_that_problem(
    four_problems, make_engine
):
    root, ids = four_problems
    engine = make_engine()
    fake = engine.as_engine()

    def broken(source, slot):
        raise InfraError("tmpfs full")

    failing = type(fake)(fake.gcc_version, broken, fake.run_suite)
    with pytest.raises(InfraError):
        run_generate(root, ids[:1], runtime.ThreadRuntime(failing, workers=2))
    assert not (root / config.PROBLEMS_DIR / ids[0]).exists()


def test_an_excluded_problem_does_not_stop_the_others(four_problems, make_engine, sparse_problem):
    root, ids = four_problems
    (root / "data" / "dataset" / "problems" / "189_D" / "AC_ref.cpp").write_text(
        sparse_problem["AC_ref.cpp"]
    )
    from mutation import dataset_gate  # noqa: F401  (the gate is not part of this unit)

    result = run_generate(root, ids, runtime.ThreadRuntime(make_engine().as_engine(), workers=3))
    assert result.excluded == ["189_D"]
    assert sorted(result.generated) == ["189_C", "189_E", "189_F"]


def test_one_worker_never_runs_two_problems_at_once(four_problems, make_engine):
    root, ids = four_problems
    in_flight, peak = [0], [0]

    class Counting(runtime.ThreadRuntime):
        def _run(self, task):
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
            try:
                time.sleep(0.05)
                return super()._run(task)
            finally:
                in_flight[0] -= 1

    run_generate(root, ids, Counting(make_engine().as_engine(), workers=1))
    assert peak[0] == 1  # a single worker thread never runs two problems at once


def test_close_shuts_the_pool_down(make_engine):
    rt = runtime.ThreadRuntime(make_engine().as_engine(), workers=2)
    rt.close()
    with pytest.raises(RuntimeError):
        rt._pool.submit(lambda: None)


def test_pool_runtime_rejects_zero_workers():
    with pytest.raises(ValueError):
        runtime.PoolRuntime(0)
