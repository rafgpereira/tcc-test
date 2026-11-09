"""Where the problems of ``run`` are evaluated: this process, threads (tests) or a pool.

Same mechanism as ``mutation.runtime`` (research R14 of the mutants): the parallelism is BETWEEN
problems; each problem is one whole task (``problem_task.evaluate_problem``) run by one worker in
its OWN engine slot (uid ``10000 + slot``, own workdir). What the main process writes does not
depend on how many workers there are nor on which finishes first.
"""

import multiprocessing
import signal
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Protocol

from evaluation import problem_task
from evaluation.problem_task import Engine, Key, ProblemTask
from evaluation.schemas.result import CombinationResult

Outcome = dict[Key, CombinationResult]


class Runtime(Protocol):
    workers: int

    def submit(self, task: ProblemTask) -> "Future[Outcome]": ...

    def close(self, *, abort: bool = False) -> None: ...


class InlineRuntime:
    """Everything in this process, one problem at a time (the default with one worker)."""

    workers = 1

    def __init__(self, engine: Engine, slot: int = 0) -> None:
        self.engine, self.slot = engine, slot

    def _run(self, task: ProblemTask) -> Outcome:
        return problem_task.evaluate_problem(task, self.engine, self.slot)

    def submit(self, task: ProblemTask) -> "Future[Outcome]":
        future: Future = Future()
        try:
            future.set_result(self._run(task))
        except BaseException as exc:  # noqa: BLE001 - re-raised by `.result()` like an executor
            future.set_exception(exc)
        return future

    def close(self, *, abort: bool = False) -> None:
        pass


class ThreadRuntime(InlineRuntime):
    """Threads with the same engine: only to test that the completion order does not matter."""

    def __init__(self, engine: Engine, workers: int, slot: int = 0) -> None:
        super().__init__(engine, slot)
        self.workers = workers
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def submit(self, task: ProblemTask) -> "Future[Outcome]":
        return self._pool.submit(self._run, task)

    def close(self, *, abort: bool = False) -> None:
        self._pool.shutdown(wait=not abort, cancel_futures=True)


_WORKER: dict = {}


def _init_worker(slot_queue) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the main process handles Ctrl+C and cleans up
    from sandbox import isolation

    slot = slot_queue.get()
    isolation.prepare_slot_workdir(slot)
    _WORKER["slot"], _WORKER["engine"] = slot, problem_task.real_engine()


def _evaluate_in_worker(task: ProblemTask) -> Outcome:
    return problem_task.evaluate_problem(task, _WORKER["engine"], _WORKER["slot"])


class PoolRuntime:
    """The real runtime: ``workers`` processes, each with its own slot."""

    def __init__(self, workers: int) -> None:
        from sandbox import isolation

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
            max_workers=workers, mp_context=context, initializer=_init_worker, initargs=(slots,)
        )

    def submit(self, task: ProblemTask) -> "Future[Outcome]":
        return self._pool.submit(_evaluate_in_worker, task)

    def close(self, *, abort: bool = False) -> None:
        """Shut the pool down; with ``abort`` (Ctrl+C, an error) do not wait for problems in flight.

        A problem in flight has nothing on disk yet (the main process writes a problem only when it
        is finished), so dropping it loses nothing: the next run redoes it.
        """
        from sandbox import isolation

        if abort:
            self._pool.shutdown(wait=False, cancel_futures=True)
            for worker in multiprocessing.active_children():
                worker.terminate()
            for worker in multiprocessing.active_children():
                worker.join(timeout=5)
        else:
            self._pool.shutdown(wait=True, cancel_futures=True)
        for slot in range(self.workers):
            isolation.kill_slot_processes(slot)
