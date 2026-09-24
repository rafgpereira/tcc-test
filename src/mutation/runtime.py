"""Where the problems of ``generate`` are processed: this process, threads (tests) or a pool.

The parallelism is BETWEEN problems (research R14): each problem is one whole, independent task
(``orchestrator.select_mutants``, unchanged) run by one worker in its OWN engine ``slot`` (uid
``10000 + slot``, own working directory), so two candidates never share a directory or a uid. The
outcome of a problem depends only on its own files and on the verdicts of the engine, never on how
many workers there are or on which finishes first; what the main process persists is the same with
1 or N workers. The mechanism (fork, a queue of slots, an initializer that prepares the workdir and
builds the engine, cleanup of the slots at the start and at the end) is the one of
``dataset.validation.runtime``.
"""

import multiprocessing
import signal
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from dataset.validation.engine import Engine
from dataset.validation.suite import Suite
from mutation import config, orchestrator
from mutation.types import Selection
from sandbox import isolation
from sandbox.types import ExecutionLimits


@dataclass(frozen=True)
class ProblemTask:
    """Everything one worker needs to mutate one problem (small, immutable, picklable)."""

    problem_id: str
    source: str
    suite: Suite
    limits: ExecutionLimits
    quota: int = config.MUTANTS_PER_PROBLEM


class Runtime(Protocol):
    workers: int

    def submit(self, task: ProblemTask) -> "Future[Selection]": ...

    def close(self) -> None: ...


class InlineRuntime:
    """Everything in this process, one problem at a time (the default with one worker)."""

    workers = 1

    def __init__(self, engine: Engine, slot: int = 0) -> None:
        self.engine, self.slot = engine, slot

    def _run(self, task: ProblemTask) -> Selection:
        return orchestrator.select_mutants(
            task.problem_id,
            task.source,
            task.suite,
            task.limits,
            engine=self.engine,
            slot=self.slot,
            quota=task.quota,
        )

    def submit(self, task: ProblemTask) -> "Future[Selection]":
        future: Future = Future()
        try:
            future.set_result(self._run(task))
        except BaseException as exc:  # noqa: BLE001 - re-raised by `.result()` like an executor
            future.set_exception(exc)
        return future

    def close(self) -> None:
        pass


class ThreadRuntime(InlineRuntime):
    """Threads with the same engine: only to test that the completion order does not matter."""

    def __init__(self, engine: Engine, workers: int, slot: int = 0) -> None:
        super().__init__(engine, slot)
        self.workers = workers
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def submit(self, task: ProblemTask) -> "Future[Selection]":
        return self._pool.submit(self._run, task)

    def close(self) -> None:
        self._pool.shutdown(cancel_futures=True)


_WORKER: dict = {}


def _init_worker(slot_queue) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the main process handles Ctrl+C and cleans up
    slot = slot_queue.get()
    isolation.prepare_slot_workdir(slot)
    from dataset.validation.engine import real_engine

    _WORKER["slot"], _WORKER["engine"] = slot, real_engine()


def _select_in_worker(task: ProblemTask) -> Selection:
    return orchestrator.select_mutants(
        task.problem_id,
        task.source,
        task.suite,
        task.limits,
        engine=_WORKER["engine"],
        slot=_WORKER["slot"],
        quota=task.quota,
    )


class PoolRuntime:
    """The real runtime: ``workers`` processes, each with its own slot."""

    def __init__(self, workers: int) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.workers = workers
        for slot in range(workers):  # leftovers of a run that was killed
            isolation.kill_slot_processes(slot)
        context = multiprocessing.get_context("fork")
        slots = context.Queue()
        for slot in range(workers):
            slots.put(slot)
        self._pool = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_init_worker,
            initargs=(slots,),
        )

    def submit(self, task: ProblemTask) -> "Future[Selection]":
        return self._pool.submit(_select_in_worker, task)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
        for slot in range(self.workers):
            isolation.kill_slot_processes(slot)
