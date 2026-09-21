"""Where candidates are evaluated: in this process, in threads (tests) or in a pool of workers.

The real thing is a pool of PROCESSES, one fixed engine `slot` per worker (uid `10000 + slot`), so
two candidates never share a working directory or a uid. The main process uses one more slot for
the sequential steps (the AC of each problem). Results always come back in candidate order
(`dataset.validation.wa.collect_wa`), so the number of workers never changes a result (FR-025).
"""

import functools
import multiprocessing
import signal
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Protocol

from dataset.validation import wa
from dataset.validation.engine import Engine, real_engine
from dataset.validation.suite import Suite
from sandbox import isolation
from sandbox.types import ExecutionLimits


class Runtime(Protocol):
    engine: Engine  # used for the sequential steps, in the main process
    main_slot: int
    window: int  # candidates in flight at once

    def submitter(self, suite: Suite, limits: ExecutionLimits) -> wa.Submit: ...

    def close(self) -> None: ...


class InlineRuntime:
    """Everything in this process, one candidate at a time (also the default of the tests)."""

    def __init__(self, engine: Engine, main_slot: int = 0) -> None:
        self.engine, self.main_slot, self.window = engine, main_slot, 1

    def submitter(self, suite: Suite, limits: ExecutionLimits) -> wa.Submit:
        return wa.inline_submit(
            functools.partial(
                wa.evaluate_candidate,
                suite=suite,
                limits=limits,
                engine=self.engine,
                slot=self.main_slot,
            )
        )

    def close(self) -> None:
        pass


class ThreadRuntime(InlineRuntime):
    """Threads with the same engine: only to test that the consumption order does not matter."""

    def __init__(self, engine: Engine, workers: int, main_slot: int = 0) -> None:
        super().__init__(engine, main_slot)
        self.window = workers * 2
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def submitter(self, suite: Suite, limits: ExecutionLimits) -> wa.Submit:
        evaluate = functools.partial(
            wa.evaluate_candidate,
            suite=suite,
            limits=limits,
            engine=self.engine,
            slot=self.main_slot,
        )
        return lambda candidate: self._pool.submit(evaluate, candidate)

    def close(self) -> None:
        self._pool.shutdown(cancel_futures=True)


_WORKER: dict = {}


def _init_worker(slot_queue) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the main process handles Ctrl+C and cleans up
    slot = slot_queue.get()
    isolation.prepare_slot_workdir(slot)
    _WORKER["slot"], _WORKER["engine"] = slot, real_engine()


def _evaluate_in_worker(candidate, suite, limits):
    return wa.evaluate_candidate(candidate, suite, limits, _WORKER["engine"], _WORKER["slot"])


class PoolRuntime:
    """The real runtime: ``workers`` processes, each with its own slot, plus the main slot."""

    def __init__(self, workers: int) -> None:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.workers = workers
        self.main_slot = workers
        self.window = workers * 2
        self.engine = real_engine()
        for slot in range(workers + 1):  # leftovers of a run that was killed
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

    def submitter(self, suite: Suite, limits: ExecutionLimits) -> wa.Submit:
        return lambda candidate: self._pool.submit(_evaluate_in_worker, candidate, suite, limits)

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
        for slot in range(self.workers + 1):
            isolation.kill_slot_processes(slot)
