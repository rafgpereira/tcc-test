"""Tests for the pool, shard checkpoint, raw problem and report schemas (T024)."""

import pytest
from pydantic import ValidationError

from dataset import config
from dataset.schemas.common import Macrocategoria as M
from dataset.schemas.pool import (
    IncorrectSolution,
    Pool,
    PoolCounts,
    PoolEntry,
    PoolProblem,
    RawProblem,
    RawTestGroup,
    RejectionReason,
    ShardCheckpoint,
)
from dataset.schemas.report import (
    CategoryAlert,
    ExtractionReport,
    PendingTriageItem,
    Provenance,
    ReportFunnel,
)


def entry(pid="1101_A", cat=M.MATEMATICA):
    return PoolEntry(
        problem_id=pid, macrocategoria=cat, raw_wa_count=120, raw_ac_count=5, source_row=7
    )


def checkpoint(**kw):
    base = dict(
        split="train",
        shard_index=3,
        rows_read=10,
        complete=True,
        funnel={"read": 10, "codeforces": 8},
        rejections={"file_io": 1},
        unique_ids=["1101_A", "1102_B"],
        eligible=[entry()],
    )
    base.update(kw)
    return ShardCheckpoint(**base)


def pool(**kw):
    base = dict(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=config.SEED,
        counts=PoolCounts(funnel={"read": 2}, rejections={}, eligible=2),
        order=["1102_B", "1101_A"],
        problems={
            "1101_A": PoolProblem(
                split="train",
                shard_index=0,
                macrocategoria=M.MATEMATICA,
                raw_wa_count=120,
                raw_ac_count=5,
                source_row=1,
            ),
            "1102_B": PoolProblem(
                split="valid",
                shard_index=0,
                macrocategoria=M.LOGICA_DIRETA,
                raw_wa_count=101,
                raw_ac_count=3,
                source_row=0,
            ),
        },
    )
    base.update(kw)
    return Pool(**base)


def raw(**kw):
    base = dict(
        problem_id="1101_A",
        split="train",
        shard_index=0,
        source_row=1,
        name="1101_A. Minimum Integer",
        description="Read n.",
        cf_contest_id=1101,
        cf_index="A",
        cf_rating=1200,
        cf_points=500.0,
        cf_tags=["math"],
        is_description_translated=False,
        time_limit_seconds=2.5,
        memory_limit_bytes=256_000_000,
        public_tests=RawTestGroup(input=["1\n"], output=["1\n"]),
        private_tests=RawTestGroup(input=[], output=[]),
        generated_tests=RawTestGroup(input=["2\n"], output=["2\n"]),
        correct_solutions=["int main(){}"],
        incorrect_solutions=[IncorrectSolution(index=4, source="int main(){return 1;}")],
    )
    base.update(kw)
    return RawProblem(**base)


def test_rejection_reasons_are_exactly_the_documented_ones():
    assert {r.value for r in RejectionReason} == {
        "not_codeforces",
        "rating_out_of_range",
        "no_allowed_tag",
        "forbidden_tag",
        "visual_dependency",
        "translated",
        "file_io",
        "no_cpp_correct",
        "no_cpp_incorrect",
        "insufficient_raw_wa",
    }


@pytest.mark.parametrize("build", [checkpoint, pool, raw])
def test_models_round_trip_through_json(build):
    model = build()
    again = type(model).model_validate_json(model.model_dump_json())
    assert again == model


@pytest.mark.parametrize("build", [checkpoint, pool, raw])
def test_schema_version_starts_at_one_and_is_enforced(build):
    model = build()
    assert model.schema_version == 1
    data = model.model_dump(mode="json") | {"schema_version": 2}
    with pytest.raises(ValidationError):
        type(model).model_validate(data)


@pytest.mark.parametrize("build", [checkpoint, pool, raw])
def test_unknown_fields_are_rejected(build):
    model = build()
    with pytest.raises(ValidationError):
        type(model).model_validate(model.model_dump(mode="json") | {"surprise": 1})


def test_pool_seed_is_the_fixed_documented_seed():
    assert pool().seed == 42 == config.SEED


def test_pool_order_must_list_every_problem_exactly_once():
    with pytest.raises(ValidationError):
        pool(order=["1101_A"])  # 1102_B missing
    with pytest.raises(ValidationError):
        pool(order=["1101_A", "1101_A"])  # duplicate
    with pytest.raises(ValidationError):
        pool(order=["1101_A", "9999_Z"])  # unknown


def test_the_shard_checkpoint_split_must_be_a_known_split():
    with pytest.raises(ValidationError):
        checkpoint(split="dev")


def test_raw_test_groups_must_have_parallel_lists():
    with pytest.raises(ValidationError):
        RawTestGroup(input=["1", "2"], output=["1"])


def test_raw_problem_keeps_the_original_index_of_each_incorrect_submission():
    problem = raw(incorrect_solutions=[IncorrectSolution(index=9, source="a")])
    assert problem.incorrect_solutions[0].index == 9


def report_kwargs(**kw):
    base = dict(
        funnel=ReportFunnel(read=10, stages={"codeforces": 8}, rejected_by_reason={}, included=0),
        pool_distribution={M.MATEMATICA: 1, M.ESTRUTURAL_OTIMIZACAO: 0, M.LOGICA_DIRETA: 0},
        distribution={M.MATEMATICA: 0, M.ESTRUTURAL_OTIMIZACAO: 0, M.LOGICA_DIRETA: 0},
        selection_final=False,
        category_alerts=[],
        pending_triage=[],
        target=200,
        deficit=200,
        provenance=Provenance(
            hf_dataset=config.HF_DATASET, hf_revision=config.HF_REVISION, seed=config.SEED
        ),
    )
    base.update(kw)
    return base


def test_report_deficit_is_the_target_minus_the_included_never_negative():
    assert ExtractionReport(**report_kwargs()).deficit == 200
    funnel = ReportFunnel(read=10, stages={}, rejected_by_reason={}, included=150)
    dist = {M.MATEMATICA: 50, M.ESTRUTURAL_OTIMIZACAO: 50, M.LOGICA_DIRETA: 50}
    assert (
        ExtractionReport(**report_kwargs(funnel=funnel, distribution=dist, deficit=50)).deficit
        == 50
    )
    over = ReportFunnel(read=10, stages={}, rejected_by_reason={}, included=210)
    dist = {M.MATEMATICA: 70, M.ESTRUTURAL_OTIMIZACAO: 70, M.LOGICA_DIRETA: 70}
    assert ExtractionReport(**report_kwargs(funnel=over, distribution=dist, deficit=0)).deficit == 0


@pytest.mark.parametrize("wrong", [0, 199, 201, -1])
def test_a_wrong_deficit_is_rejected(wrong):
    with pytest.raises(ValidationError):
        ExtractionReport(**report_kwargs(deficit=wrong))


def test_included_must_match_the_distribution():
    funnel = ReportFunnel(read=10, stages={}, rejected_by_reason={}, included=5)
    with pytest.raises(ValidationError):
        ExtractionReport(**report_kwargs(funnel=funnel, deficit=195))


def test_report_round_trips_and_carries_alerts_and_pending_items():
    report = ExtractionReport(
        **report_kwargs(
            category_alerts=[CategoryAlert(macrocategoria=M.MATEMATICA, count=25, threshold=30)],
            pending_triage=[PendingTriageItem(problem_id="1234_C", stage="selection", reason="WA")],
        )
    )
    assert ExtractionReport.model_validate_json(report.model_dump_json()) == report
    assert report.schema_version == 1
    with pytest.raises(ValidationError):
        PendingTriageItem(problem_id="1234_C", stage="other", reason="x")
