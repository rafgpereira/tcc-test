"""Tests for the streaming extraction with a fake in-memory dataset, no network (T026)."""

import gzip
import json
import os
import random
import stat

import pytest

from dataset import config
from dataset.extraction import stream
from dataset.persistence import store
from dataset.schemas.pool import Pool, RawProblem, ShardCheckpoint


class FakeSplit:
    """Stands in for one split of the Hugging Face dataset: several shards of rows."""

    def __init__(self, name, shards, log, fail_at=None):
        self.name, self.shards, self.log, self.fail_at = name, shards, log, fail_at

    @property
    def n_shards(self):
        return len(self.shards)

    def shard_rows(self, index):
        self.log.append((self.name, index))
        rows = self.shards[index]

        def generate():
            for position, row in enumerate(rows):
                if self.fail_at == (self.name, index, position):
                    raise RuntimeError("network down")
                yield row

        return generate()


@pytest.fixture
def fake_hf(monkeypatch):
    def install(data, fail_at=None):
        log = []
        monkeypatch.setattr(
            stream, "open_split", lambda split: FakeSplit(split, data[split], log, fail_at)
        )
        return log

    return install


@pytest.fixture
def unique(row_factory):
    def build(i, **overrides):
        return row_factory(
            cf_contest_id=2000 + i, cf_index="A", name=f"{2000 + i}_A. Problem", **overrides
        )

    return build


def raw_dir(root):
    return root / config.RAW_DIR


def read_raw(root, problem_id):
    return RawProblem.model_validate(store.read_json_gz(raw_dir(root) / f"{problem_id}.json.gz"))


def simple_data(unique, n_train_shards=3):
    return {
        "train": [[unique(i)] for i in range(n_train_shards)],
        "valid": [[unique(10)]],
        "test": [[unique(20)]],
    }


def test_splits_and_shards_are_read_in_order(fake_hf, unique, tmp_path):
    log = fake_hf(simple_data(unique))
    stream.extract(tmp_path)
    assert log == [("train", 0), ("train", 1), ("train", 2), ("valid", 0), ("test", 0)]


def test_the_splits_option_limits_and_orders_the_splits(fake_hf, unique, tmp_path):
    log = fake_hf(simple_data(unique))
    pool = stream.extract(tmp_path, splits=("test", "valid"))
    assert log == [("test", 0), ("valid", 0)]
    assert sorted(pool.problems) == ["2010_A", "2020_A"]


def test_the_first_occurrence_of_a_problem_wins_across_shards_and_splits(fake_hf, unique, tmp_path):
    data = {
        "train": [[unique(0)], [unique(1), unique(0)]],
        "valid": [[unique(0)]],
        "test": [[]],
    }
    fake_hf(data)
    pool = stream.extract(tmp_path)
    assert sorted(pool.problems) == ["2000_A", "2001_A"]
    assert pool.problems["2000_A"].split == "train"
    assert pool.problems["2000_A"].shard_index == 0
    assert pool.counts.funnel["not_translated"] == 4
    assert pool.counts.funnel["unique_id"] == 2, "the two later copies are duplicates"


def test_the_time_limit_is_seconds_plus_nanos(fake_hf, unique, tmp_path):
    row = unique(0, time_limit={"seconds": 2, "nanos": 500_000_000})
    fake_hf({"train": [[row]], "valid": [[]], "test": [[]]})
    stream.extract(tmp_path)
    assert read_raw(tmp_path, "2000_A").time_limit_seconds == 2.5


def test_the_raw_file_keeps_only_cpp_solutions_and_the_original_indices(fake_hf, unique, tmp_path):
    languages = [3, 2, 3, 2] + [2] * 98
    solutions = ["p0", "c1", "p2", "c3"] + [f"c{i}" for i in range(4, 102)]
    row = unique(0, incorrect_solutions={"language": languages, "solution": solutions})
    fake_hf({"train": [[row]], "valid": [[]], "test": [[]]})
    stream.extract(tmp_path)
    raw = read_raw(tmp_path, "2000_A")
    assert len(raw.incorrect_solutions) == 100
    assert [s.index for s in raw.incorrect_solutions][:4] == [1, 3, 4, 5]
    assert raw.incorrect_solutions[0].source == "c1"
    assert all(s.startswith("int main") for s in raw.correct_solutions)
    assert len(raw.correct_solutions) == 2, "the Python correct solution is dropped"
    assert raw.public_tests.input == ["1\n"] and raw.generated_tests.output == ["3\n", "4\n"]
    assert (raw.cf_contest_id, raw.cf_index, raw.split) == (2000, "A", "train")


def test_raw_files_exist_only_for_pool_problems_and_no_temp_files_remain(fake_hf, unique, tmp_path):
    data = {
        "train": [[unique(0), unique(1, source=1), unique(2, cpp_wa=5)]],
        "valid": [[]],
        "test": [[]],
    }
    fake_hf(data)
    pool = stream.extract(tmp_path)
    assert [p.name for p in raw_dir(tmp_path).iterdir()] == ["2000_A.json.gz"]
    assert sorted(pool.problems) == ["2000_A"]


def test_raw_files_are_identical_across_independent_runs(fake_hf, unique, tmp_path):
    fake_hf(simple_data(unique))
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    stream.extract(first)
    stream.extract(second)
    for name in os.listdir(raw_dir(first)):
        assert (raw_dir(first) / name).read_bytes() == (raw_dir(second) / name).read_bytes()
    assert (first / config.STAGING_DIR / "pool.json").read_bytes() == (
        second / config.STAGING_DIR / "pool.json"
    ).read_bytes()


def test_gzip_content_is_json_and_deterministic(fake_hf, unique, tmp_path):
    fake_hf(simple_data(unique, 1))
    stream.extract(tmp_path)
    path = raw_dir(tmp_path) / "2000_A.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle)["problem_id"] == "2000_A"
    assert path.read_bytes()[4:8] == b"\x00\x00\x00\x00", "gzip mtime is fixed at 0"


def test_a_shard_checkpoint_is_written_only_after_that_shards_raw_files(
    fake_hf, unique, tmp_path, monkeypatch
):
    events = []
    real_gz, real_json = store.atomic_write_json_gz, store.atomic_write_json

    def spy_gz(path, obj):
        events.append(("raw", path.name))
        real_gz(path, obj)

    def spy_json(path, obj):
        events.append(("json", path.name))
        real_json(path, obj)

    monkeypatch.setattr(store, "atomic_write_json_gz", spy_gz)
    monkeypatch.setattr(store, "atomic_write_json", spy_json)
    data = {"train": [[unique(0), unique(1)], [unique(2)]], "valid": [[]], "test": [[]]}
    fake_hf(data)
    stream.extract(tmp_path)
    assert events == [
        ("raw", "2000_A.json.gz"),
        ("raw", "2001_A.json.gz"),
        ("json", "train-00000.json"),
        ("raw", "2002_A.json.gz"),
        ("json", "train-00001.json"),
        ("json", "valid-00000.json"),
        ("json", "test-00000.json"),
        ("json", "pool.json"),
    ]


def test_a_rerun_skips_completed_shards_and_rewrites_nothing(
    fake_hf, unique, tmp_path, monkeypatch
):
    fake_hf(simple_data(unique))
    stream.extract(tmp_path)
    before = {p.name: p.stat().st_mtime_ns for p in raw_dir(tmp_path).iterdir()}

    writes = []
    monkeypatch.setattr(store, "atomic_write_json_gz", lambda path, obj: writes.append(path))
    log = fake_hf(simple_data(unique))
    pool = stream.extract(tmp_path)

    assert log == [], "no shard is opened again"
    assert writes == []
    assert {p.name: p.stat().st_mtime_ns for p in raw_dir(tmp_path).iterdir()} == before
    assert len(pool.problems) == 5


def test_a_run_interrupted_mid_shard_resumes_to_the_same_pool(fake_hf, unique, tmp_path):
    data = {
        "train": [[unique(0), unique(1)], [unique(2), unique(3)]],
        "valid": [[unique(4)]],
        "test": [[]],
    }
    fake_hf(data, fail_at=("train", 1, 1))
    with pytest.raises(RuntimeError):
        stream.extract(tmp_path)
    checkpoints = sorted(p.name for p in (tmp_path / config.SHARDS_DIR).iterdir())
    assert checkpoints == ["train-00000.json"], "the interrupted shard has no checkpoint"

    log = fake_hf(data)
    resumed = stream.extract(tmp_path)
    assert log == [("train", 1), ("valid", 0), ("test", 0)], "shard 0 is not read again"

    fresh_root = tmp_path / "fresh"
    fresh_root.mkdir()
    fake_hf(data)
    assert resumed == stream.extract(fresh_root)
    assert len(list(raw_dir(tmp_path).iterdir())) == 5


def test_resuming_keeps_duplicate_detection_across_the_interruption(fake_hf, unique, tmp_path):
    """A problem that failed a later stage in a finished shard is still a known id."""
    bad = unique(
        0, input_file="input.txt", output_file="output.txt"
    )  # passes unique, fails file_io
    data = {"train": [[bad], [unique(1), bad]], "valid": [[]], "test": [[]]}
    fake_hf(data, fail_at=("train", 1, 1))
    with pytest.raises(RuntimeError):
        stream.extract(tmp_path)
    fake_hf(data)
    resumed = stream.extract(tmp_path)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    fake_hf(data)
    assert resumed.counts == stream.extract(fresh).counts


def test_the_pool_order_is_sorted_then_shuffled_with_the_documented_seed(fake_hf, unique, tmp_path):
    data = {"train": [[unique(i) for i in range(8)]], "valid": [[]], "test": [[]]}
    fake_hf(data)
    pool = stream.extract(tmp_path)
    expected = sorted(f"{2000 + i}_A" for i in range(8))
    random.Random("42:pool").shuffle(expected)
    assert pool.order == expected
    assert pool.seed == 42 == config.SEED


def test_the_seed_option_changes_the_order_and_is_recorded(fake_hf, unique, tmp_path):
    data = {"train": [[unique(i) for i in range(8)]], "valid": [[]], "test": [[]]}
    fake_hf(data)
    pool = stream.extract(tmp_path, seed=7)
    expected = sorted(f"{2000 + i}_A" for i in range(8))
    random.Random("7:pool").shuffle(expected)
    assert pool.order == expected and pool.seed == 7


def test_the_pool_file_is_valid_and_matches_the_returned_pool(fake_hf, unique, tmp_path):
    fake_hf(simple_data(unique))
    pool = stream.extract(tmp_path)
    on_disk = Pool.model_validate(store.read_json(tmp_path / config.STAGING_DIR / "pool.json"))
    assert on_disk == pool
    assert (pool.hf_dataset, pool.hf_revision) == (config.HF_DATASET, config.HF_REVISION)


def test_limit_rows_limits_the_rows_read_per_split(fake_hf, unique, tmp_path):
    data = {
        "train": [[unique(0), unique(1), unique(2)], [unique(3), unique(4), unique(5)]],
        "valid": [[unique(10), unique(11)]],
        "test": [[]],
    }
    log = fake_hf(data)
    pool = stream.extract(tmp_path, limit_rows=4)
    assert sorted(pool.problems) == ["2000_A", "2001_A", "2002_A", "2003_A", "2010_A", "2011_A"]
    first = ShardCheckpoint.model_validate(
        store.read_json(tmp_path / config.SHARDS_DIR / "train-00000.json")
    )
    second = ShardCheckpoint.model_validate(
        store.read_json(tmp_path / config.SHARDS_DIR / "train-00001.json")
    )
    assert (first.rows_read, first.complete) == (3, True), "the shard ended before the limit"
    assert (second.rows_read, second.complete) == (1, False), "the limit stopped it"
    assert ("train", 1) in log


def test_an_incomplete_shard_is_redone_by_a_later_full_run(fake_hf, unique, tmp_path):
    data = {"train": [[unique(0), unique(1), unique(2)]], "valid": [[]], "test": [[]]}
    fake_hf(data)
    stream.extract(tmp_path, limit_rows=2)
    log = fake_hf(data)
    pool = stream.extract(tmp_path)
    assert ("train", 0) in log
    assert len(pool.problems) == 3


def test_the_funnel_counts_the_rows_that_survive_each_stage(fake_hf, unique, tmp_path):
    rows = [
        unique(0, source=1),  # not Codeforces
        unique(1, cf_rating=900),  # rating
        unique(2, cf_tags=["number theory"]),  # no allowed tag
        unique(3, cf_tags=["dp", "geometry"]),  # forbidden tag
        unique(4, description="See the figure."),  # visual
        unique(5, is_description_translated=True),  # translated
        unique(6),  # eligible
        unique(7, input_file="input.txt"),  # file I/O
        unique(8, cpp_ac=0),  # no C++ correct
        unique(9, cpp_wa=50),  # too few raw WA
    ]
    duplicate = unique(6)
    fake_hf({"train": [rows], "valid": [[duplicate]], "test": [[]]})
    pool = stream.extract(tmp_path)

    assert pool.counts.funnel == {
        "read": 11,
        "codeforces": 10,
        "rating_1000_1600": 9,
        "has_allowed_tag": 8,
        "no_forbidden_tag": 7,
        "no_visual_term": 6,
        "not_translated": 5,  # rows 6, 7, 8, 9 and the duplicate of 6
        "unique_id": 4,
        "no_file_io": 3,
        "has_cpp_solutions": 2,
        "enough_raw_wa": 1,
    }
    assert pool.counts.eligible == 1 and sorted(pool.problems) == ["2006_A"]
    assert pool.counts.rejections == {
        "not_codeforces": 1,
        "rating_out_of_range": 1,
        "no_allowed_tag": 1,
        "forbidden_tag": 1,
        "visual_dependency": 1,
        "translated": 1,
        "file_io": 1,
        "no_cpp_correct": 1,
        "insufficient_raw_wa": 1,
    }


def test_the_checkpoint_lists_every_unique_id_and_the_eligible_entries(fake_hf, unique, tmp_path):
    rows = [unique(0), unique(1, input_file="input.txt")]
    fake_hf({"train": [rows], "valid": [[]], "test": [[]]})
    stream.extract(tmp_path)
    ckpt = ShardCheckpoint.model_validate(
        store.read_json(tmp_path / config.SHARDS_DIR / "train-00000.json")
    )
    assert ckpt.unique_ids == ["2000_A", "2001_A"]
    assert [e.problem_id for e in ckpt.eligible] == ["2000_A"]
    entry = ckpt.eligible[0]
    assert (entry.macrocategoria.value, entry.raw_wa_count, entry.raw_ac_count) == (
        "estrutural_otimizacao",
        100,
        2,
    )
    assert entry.source_row == 0 and ckpt.rows_read == 2 and ckpt.complete


def test_the_work_dir_is_private(fake_hf, unique, tmp_path):
    fake_hf(simple_data(unique, 1))
    stream.extract(tmp_path)
    for path in (tmp_path / config.WORK_DIR, raw_dir(tmp_path), tmp_path / config.SHARDS_DIR):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_an_empty_dataset_gives_an_empty_pool(fake_hf, tmp_path):
    fake_hf({"train": [[]], "valid": [[]], "test": [[]]})
    pool = stream.extract(tmp_path)
    assert pool.order == [] and pool.problems == {} and pool.counts.eligible == 0
