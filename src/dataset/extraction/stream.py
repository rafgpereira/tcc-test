"""Streaming extraction of the eligible problems (spec FR-001 to FR-007, FR-024).

One pass over the three splits, on a pinned revision of the dataset. Rows are evaluated and
classified inline, and only the eligible problems are written (``staging/raw/<id>.json.gz``); the
repository is never downloaded as a whole. Each shard is checkpointed AFTER its raw files, so an
interruption only redoes the shard in progress. The processing order of the pool is the sorted ids
shuffled with the fixed seed (Constitution, Principle II).
"""

from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from dataset import config
from dataset.filtering.classification import classify
from dataset.filtering.eligibility import evaluate
from dataset.persistence import store
from dataset.schemas.pool import (
    IncorrectSolution,
    Pool,
    PoolCounts,
    PoolEntry,
    PoolProblem,
    RawProblem,
    RawTestGroup,
    ShardCheckpoint,
)
from dataset.schemas.pool import (
    RejectionReason as R,
)

# Eligibility stages in the order of the funnel. A row is counted in a stage only if it passed
# every earlier stage, which reproduces the funnel measured on 2026-09-19 (methodology 1.2).
STAGES = (
    "codeforces",
    "rating_1000_1600",
    "has_allowed_tag",
    "no_forbidden_tag",
    "no_visual_term",
    "not_translated",
    "unique_id",
    "no_file_io",
    "has_cpp_solutions",
    "enough_raw_wa",
)
_STAGE_REASONS: dict[str, set[R]] = {
    "codeforces": {R.NOT_CODEFORCES},
    "rating_1000_1600": {R.RATING_OUT_OF_RANGE},
    "has_allowed_tag": {R.NO_ALLOWED_TAG},
    "no_forbidden_tag": {R.FORBIDDEN_TAG},
    "no_visual_term": {R.VISUAL_DEPENDENCY},
    "not_translated": {R.TRANSLATED},
    "unique_id": set(),  # decided by the ids already seen, not by the row alone
    "no_file_io": {R.FILE_IO},
    "has_cpp_solutions": {R.NO_CPP_CORRECT, R.NO_CPP_INCORRECT},
    "enough_raw_wa": {R.INSUFFICIENT_RAW_WA},
}


class SplitSource(Protocol):
    """One split of the dataset, readable shard by shard."""

    n_shards: int

    def shard_rows(self, index: int) -> Iterator[Mapping[str, Any]]: ...


class _HuggingFaceSplit:
    def __init__(self, split: str) -> None:
        import datasets  # imported here so the CLI and the tests do not need the network stack

        self._ds = datasets.load_dataset(
            config.HF_DATASET, split=split, streaming=True, revision=config.HF_REVISION
        )
        self.n_shards = self._ds.n_shards

    def shard_rows(self, index: int) -> Iterator[Mapping[str, Any]]:
        return iter(self._ds.shard(num_shards=self.n_shards, index=index))


def open_split(split: str) -> SplitSource:
    """Open a split in streaming mode on the pinned revision (tests replace this function)."""
    return _HuggingFaceSplit(split)


def problem_id(row: Mapping[str, Any]) -> str:
    return f"{row['cf_contest_id']}_{row['cf_index']}"


def _cpp_sources(solutions: Mapping[str, Any] | None) -> list[tuple[int, str]]:
    languages = (solutions or {}).get("language") or []
    sources = (solutions or {}).get("solution") or []
    return [
        (index, source)
        for index, (language, source) in enumerate(zip(languages, sources))
        if language == config.HF_LANGUAGE_CPP
    ]


def _tests(row: Mapping[str, Any], key: str) -> RawTestGroup:
    group = row.get(key) or {}
    return RawTestGroup(
        input=list(group.get("input") or []), output=list(group.get("output") or [])
    )


def to_raw(row: Mapping[str, Any], split: str, shard_index: int, source_row: int) -> RawProblem:
    """Convert an eligible dataset row to the module's own raw format."""
    limit = row.get("time_limit") or {}
    return RawProblem(
        problem_id=problem_id(row),
        split=split,
        shard_index=shard_index,
        source_row=source_row,
        name=row.get("name") or "",
        description=row.get("description") or "",
        cf_contest_id=row["cf_contest_id"],
        cf_index=row["cf_index"],
        cf_rating=row["cf_rating"],
        cf_points=row.get("cf_points") or 0.0,
        cf_tags=list(row.get("cf_tags") or []),
        is_description_translated=bool(row.get("is_description_translated")),
        time_limit_seconds=(limit.get("seconds") or 0) + (limit.get("nanos") or 0) / 1e9,
        memory_limit_bytes=row.get("memory_limit_bytes") or 0,
        public_tests=_tests(row, "public_tests"),
        private_tests=_tests(row, "private_tests"),
        generated_tests=_tests(row, "generated_tests"),
        correct_solutions=[source for _, source in _cpp_sources(row.get("solutions"))],
        incorrect_solutions=[
            IncorrectSolution(index=index, source=source)
            for index, source in _cpp_sources(row.get("incorrect_solutions"))
        ],
    )


def _checkpoint_path(root: Path, split: str, shard_index: int) -> Path:
    return root / config.SHARDS_DIR / f"{split}-{shard_index:05d}.json"


def _process_shard(
    root: Path,
    split: str,
    shard_index: int,
    rows: Iterator[Mapping[str, Any]],
    seen: set[str],
    row_limit: int | None,
) -> ShardCheckpoint:
    funnel = dict.fromkeys(("read", *STAGES), 0)
    rejections: Counter[str] = Counter()
    unique_ids: list[str] = []
    eligible: list[PoolEntry] = []
    rows_read, truncated = 0, False

    for position, row in enumerate(rows):
        if row_limit is not None and position >= row_limit:
            truncated = True  # a row exists beyond the limit, so the shard is not finished
            break
        rows_read += 1
        funnel["read"] += 1
        reasons = set(evaluate(row))
        for reason in reasons:
            rejections[reason.value] += 1

        for stage in STAGES:
            if stage == "unique_id":
                pid = problem_id(row)
                if pid in seen:
                    break
                seen.add(pid)
                unique_ids.append(pid)
            elif _STAGE_REASONS[stage] & reasons:
                break
            funnel[stage] += 1
        else:
            raw = to_raw(row, split, shard_index, position)
            store.atomic_write_json_gz(
                root / config.RAW_DIR / f"{raw.problem_id}.json.gz", raw.model_dump(mode="json")
            )
            eligible.append(
                PoolEntry(
                    problem_id=raw.problem_id,
                    macrocategoria=classify(raw.cf_tags),
                    raw_wa_count=len(raw.incorrect_solutions),
                    raw_ac_count=len(raw.correct_solutions),
                    source_row=position,
                )
            )

    return ShardCheckpoint(
        split=split,
        shard_index=shard_index,
        rows_read=rows_read,
        complete=not truncated,
        funnel=funnel,
        rejections=dict(sorted(rejections.items())),
        unique_ids=unique_ids,
        eligible=eligible,
    )


def build_pool(root: Path, splits: Sequence[str], seed: int = config.SEED) -> Pool:
    """Build the pool from the shard checkpoints, in the global reading order."""
    funnel = dict.fromkeys(("read", *STAGES), 0)
    rejections: Counter[str] = Counter()
    problems: dict[str, PoolProblem] = {}
    shards_dir = root / config.SHARDS_DIR
    for split in splits:
        paths = sorted(shards_dir.glob(f"{split}-*.json"))
        for path in paths:
            checkpoint = ShardCheckpoint.model_validate(store.read_json(path))
            for key, value in checkpoint.funnel.items():
                funnel[key] += value
            rejections.update(checkpoint.rejections)
            for entry in checkpoint.eligible:
                problems[entry.problem_id] = PoolProblem(
                    split=split,
                    shard_index=checkpoint.shard_index,
                    macrocategoria=entry.macrocategoria,
                    raw_wa_count=entry.raw_wa_count,
                    raw_ac_count=entry.raw_ac_count,
                    source_row=entry.source_row,
                )
    order = sorted(problems)
    config.seeded_random("pool", seed).shuffle(order)
    return Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=seed,
        counts=PoolCounts(
            funnel=funnel, rejections=dict(sorted(rejections.items())), eligible=len(problems)
        ),
        order=order,
        problems=problems,
    )


def extract(
    root: Path,
    splits: Sequence[str] = config.SPLITS,
    limit_rows: int | None = None,
    seed: int = config.SEED,
    progress: Callable[[str], None] | None = None,
) -> Pool:
    """Extract the eligible problems and write the pool. Safe to run again after any failure.

    Shards that already have a COMPLETE checkpoint are skipped; their unique ids are loaded first so
    the "first occurrence wins" rule gives the same result as an uninterrupted run.
    """
    say = progress or (lambda message: None)
    root = Path(root)
    store.ensure_work_dir(root)
    seen: set[str] = set()

    for split in splits:
        source = open_split(split)
        consumed = 0
        for shard_index in range(source.n_shards):
            path = _checkpoint_path(root, split, shard_index)
            if path.exists():
                done = ShardCheckpoint.model_validate(store.read_json(path))
                if done.complete:
                    seen.update(done.unique_ids)
                    consumed += done.rows_read
                    say(f"{split} shard {shard_index + 1}/{source.n_shards}: already done")
                    continue
            row_limit = None if limit_rows is None else limit_rows - consumed
            if row_limit is not None and row_limit <= 0:
                break
            checkpoint = _process_shard(
                root, split, shard_index, source.shard_rows(shard_index), seen, row_limit
            )
            store.atomic_write_json(path, checkpoint)
            consumed += checkpoint.rows_read
            say(
                f"{split} shard {shard_index + 1}/{source.n_shards}: {checkpoint.rows_read} rows, "
                f"{len(checkpoint.eligible)} eligible"
            )

    pool = build_pool(root, splits, seed)
    store.atomic_write_json(root / config.STAGING_DIR / "pool.json", pool)
    say(f"pool: {pool.counts.eligible} eligible problems")
    return pool
