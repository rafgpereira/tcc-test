"""Schemas of the extraction stage: rejection reasons, shard checkpoints, pool and raw problems."""

from enum import Enum

from pydantic import model_validator

from dataset.schemas.common import Macrocategoria, Schema, SchemaVersion, Split


class RejectionReason(str, Enum):
    """Why a row is not eligible (spec FR-004, FR-005). A row can have several reasons."""

    NOT_CODEFORCES = "not_codeforces"
    RATING_OUT_OF_RANGE = "rating_out_of_range"  # includes a missing rating
    NO_ALLOWED_TAG = "no_allowed_tag"
    FORBIDDEN_TAG = "forbidden_tag"
    VISUAL_DEPENDENCY = "visual_dependency"
    TRANSLATED = "translated"
    FILE_IO = "file_io"
    NO_CPP_CORRECT = "no_cpp_correct"
    NO_CPP_INCORRECT = "no_cpp_incorrect"
    INSUFFICIENT_RAW_WA = "insufficient_raw_wa"  # fewer than 100 raw C++ incorrect submissions


class PoolEntry(Schema):
    """An eligible problem found while reading one shard."""

    problem_id: str
    macrocategoria: Macrocategoria
    raw_wa_count: int
    raw_ac_count: int
    source_row: int  # 0-based position of the row inside its shard


class ShardCheckpoint(Schema):
    """Written after the raw files of a shard; its existence marks the shard as done."""

    schema_version: SchemaVersion = 1
    split: Split
    shard_index: int
    rows_read: int
    complete: bool  # False when --limit-rows stopped the shard early
    funnel: dict[str, int]
    rejections: dict[str, int]
    unique_ids: list[str]  # every id that passed the uniqueness stage, eligible or not
    eligible: list[PoolEntry]


class PoolProblem(Schema):
    split: Split
    shard_index: int
    macrocategoria: Macrocategoria
    raw_wa_count: int
    raw_ac_count: int
    source_row: int


class PoolCounts(Schema):
    funnel: dict[str, int]  # rows that survive each stage, in order
    rejections: dict[str, int]  # rows with each rejection reason (a row can count in several)
    eligible: int


class Pool(Schema):
    """The eligible problems and the order in which they are processed."""

    schema_version: SchemaVersion = 1
    hf_dataset: str
    hf_revision: str
    seed: int
    counts: PoolCounts
    order: list[str]
    problems: dict[str, PoolProblem]

    @model_validator(mode="after")
    def _order_lists_every_problem_once(self) -> "Pool":
        if len(set(self.order)) != len(self.order) or set(self.order) != set(self.problems):
            raise ValueError("`order` must list every problem of `problems` exactly once")
        return self


class RawTestGroup(Schema):
    """Parallel lists of inputs and expected outputs, as the dataset provides them."""

    input: list[str]
    output: list[str]

    @model_validator(mode="after")
    def _lists_are_parallel(self) -> "RawTestGroup":
        if len(self.input) != len(self.output):
            raise ValueError("`input` and `output` must have the same length")
        return self


class IncorrectSolution(Schema):
    index: int  # position in the dataset `incorrect_solutions` list (all languages)
    source: str


class RawProblem(Schema):
    """Everything the validation needs about one eligible problem (own format, not the dataset's)."""

    schema_version: SchemaVersion = 1
    problem_id: str
    split: Split
    shard_index: int
    source_row: int
    name: str
    description: str
    cf_contest_id: int
    cf_index: str
    cf_rating: int
    cf_points: float
    cf_tags: list[str]
    is_description_translated: bool
    time_limit_seconds: float
    memory_limit_bytes: int
    public_tests: RawTestGroup
    private_tests: RawTestGroup
    generated_tests: RawTestGroup
    correct_solutions: list[str]  # C++ only, original order
    incorrect_solutions: list[IncorrectSolution]  # C++ only, original order
