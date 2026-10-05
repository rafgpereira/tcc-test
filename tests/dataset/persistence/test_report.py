"""Tests for the extraction report: funnel, distribution and alerts (T025; FR-018, FR-018a)."""

import json
import os
import stat

from dataset import config
from dataset.persistence import report as rep
from dataset.persistence import store
from dataset.schemas.common import Macrocategoria as M
from dataset.schemas.pool import Pool, PoolCounts, PoolProblem
from dataset.schemas.report import PendingTriageItem


def make_pool(cats=(M.MATEMATICA, M.ESTRUTURAL_OTIMIZACAO, M.LOGICA_DIRETA)):
    problems = {
        f"{1000 + i}_A": PoolProblem(
            split="train",
            shard_index=0,
            macrocategoria=cat,
            raw_wa_count=120,
            raw_ac_count=3,
            source_row=i,
        )
        for i, cat in enumerate(cats)
    }
    counts = PoolCounts(
        funnel={"read": 50, "codeforces": 30, "enough_raw_wa": len(cats)},
        rejections={"file_io": 4, "translated": 2},
        eligible=len(cats),
    )
    return Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=config.SEED,
        counts=counts,
        order=sorted(problems),
        problems=problems,
    )


def sample(mat, est, log):
    return [M.MATEMATICA] * mat + [M.ESTRUTURAL_OTIMIZACAO] * est + [M.LOGICA_DIRETA] * log


def test_funnel_counts_come_from_the_pool_by_reason_and_stage():
    report = rep.build_report(make_pool())
    assert report.funnel.read == 50
    assert report.funnel.stages == {"codeforces": 30, "enough_raw_wa": 3}
    assert report.funnel.rejected_by_reason == {"file_io": 4, "translated": 2}


def test_the_funnel_stages_keep_the_funnel_order_after_the_json_roundtrip():
    # The stored pool has sorted keys, so a report built from the file must not follow that order
    # (found in the first real run: `report` listed the stages alphabetically).
    funnel = {"read": 100, **{stage: 90 - i for i, stage in enumerate(config.FUNNEL_STAGES)}}
    pool = make_pool()
    pool.counts.funnel = funnel
    stored = Pool.model_validate_json(store.dumps_json(pool))
    assert list(stored.counts.funnel) != ["read", *config.FUNNEL_STAGES]
    report = rep.build_report(stored)
    assert list(report.funnel.stages) == list(config.FUNNEL_STAGES)
    stages_in_markdown = [
        line.split("|")[1].strip()
        for line in rep.render_markdown(report).splitlines()
        if line.startswith("| ") and line.split("|")[1].strip() in config.FUNNEL_STAGES
    ]
    assert stages_in_markdown[: len(config.FUNNEL_STAGES)] == list(config.FUNNEL_STAGES)


def test_discarded_by_reason_are_reported_as_given():
    report = rep.build_report(make_pool(), discarded_by_reason={"insufficient_wa": 7})
    assert report.funnel.discarded_by_reason == {"insufficient_wa": 7}


def test_the_pool_distribution_counts_the_eligible_problems_by_category():
    pool = make_pool((M.MATEMATICA, M.MATEMATICA, M.LOGICA_DIRETA))
    report = rep.build_report(pool)
    assert report.pool_distribution == {
        M.MATEMATICA: 2,
        M.ESTRUTURAL_OTIMIZACAO: 0,
        M.LOGICA_DIRETA: 1,
    }


def test_the_sample_distribution_lists_every_category_even_when_zero():
    report = rep.build_report(make_pool(), included=sample(3, 0, 1))
    assert report.distribution == {M.MATEMATICA: 3, M.ESTRUTURAL_OTIMIZACAO: 0, M.LOGICA_DIRETA: 1}
    assert report.funnel.included == 4


def test_deficit_is_the_target_minus_the_included():
    assert rep.build_report(make_pool()).deficit == 200
    assert rep.build_report(make_pool(), included=sample(80, 60, 40)).deficit == 20
    assert rep.build_report(make_pool(), included=sample(80, 80, 60)).deficit == 0
    assert rep.build_report(make_pool(), included=sample(50, 50, 50), target=100).deficit == 0


def test_alerts_list_exactly_the_categories_below_30_with_name_and_count():
    report = rep.build_report(make_pool(), included=sample(25, 100, 75), selection_final=True)
    assert [(a.macrocategoria, a.count, a.threshold) for a in report.category_alerts] == [
        (M.MATEMATICA, 25, 30)
    ]


def test_exactly_30_is_not_below_the_threshold():
    report = rep.build_report(make_pool(), included=sample(30, 100, 70), selection_final=True)
    assert report.category_alerts == []


def test_several_categories_can_alert_at_once():
    report = rep.build_report(make_pool(), included=sample(10, 170, 20), selection_final=True)
    assert {a.macrocategoria for a in report.category_alerts} == {M.MATEMATICA, M.LOGICA_DIRETA}


def test_no_alert_when_every_category_has_30_or_more():
    report = rep.build_report(make_pool(), included=sample(60, 70, 70), selection_final=True)
    assert report.category_alerts == []


def test_no_alert_before_the_selection_is_final():
    """A partial sample naturally has few problems per category, so alerts wait for the end."""
    report = rep.build_report(make_pool(), included=sample(5, 5, 5), selection_final=False)
    assert report.category_alerts == []


def test_the_alert_is_informative_and_changes_nothing():
    included = sample(25, 100, 75)
    before = list(included)
    with_alert = rep.build_report(make_pool(), included=included, selection_final=True)
    without = rep.build_report(make_pool(), included=included, selection_final=False)
    assert included == before, "inputs are not modified"
    assert with_alert.deficit == without.deficit == 0
    assert with_alert.distribution == without.distribution
    assert with_alert.funnel.included == without.funnel.included == 200


PENDING = [PendingTriageItem(problem_id="1234_C", stage="selection", reason="AC diverged")]


def test_pending_triage_is_listed_with_its_reason_in_every_situation():
    report = rep.build_report(make_pool(), pending_triage=PENDING)
    text = rep.render_markdown(report)
    assert report.pending_triage == PENDING
    assert "1234_C" in text and "AC diverged" in text


def test_triage_is_deferred_while_the_run_can_still_reach_the_target():
    """D17: no manual inspection while other pool problems can still fill the sample."""
    text = rep.render_markdown(rep.build_report(make_pool(), pending_triage=PENDING))
    assert "Triagem adiada" in text and "PENDENTE DE TRIAGEM" not in text
    assert "só serão inspecionados" in text


def test_triage_is_deferred_and_needs_no_inspection_when_the_target_was_reached():
    report = rep.build_report(
        make_pool(), included=sample(70, 60, 70), selection_final=True, pending_triage=PENDING
    )
    text = rep.render_markdown(report)
    assert report.deficit == 0
    assert "Triagem adiada" in text and "PENDENTE DE TRIAGEM" not in text
    assert "não exigem inspeção" in text


def test_triage_needs_inspection_only_when_the_pool_ended_with_a_deficit():
    report = rep.build_report(
        make_pool(), included=sample(3, 3, 3), selection_final=True, pending_triage=PENDING
    )
    text = rep.render_markdown(report)
    assert report.deficit > 0
    assert "PENDENTE DE TRIAGEM" in text and "exige agora inspeção individual" in text
    assert "Triagem adiada" not in text
    assert "sem limiar de tolerância" in text


def test_the_markdown_has_no_pending_highlight_when_the_list_is_empty():
    text = rep.render_markdown(rep.build_report(make_pool()))
    assert "PENDENTE DE TRIAGEM" not in text


def test_the_markdown_highlights_alerts_with_category_and_count():
    report = rep.build_report(make_pool(), included=sample(25, 100, 75), selection_final=True)
    text = rep.render_markdown(report)
    assert "ALERTA" in text and "matematica" in text and "25" in text
    assert "ALERTA" not in rep.render_markdown(rep.build_report(make_pool()))


def test_the_markdown_shows_the_deficit():
    text = rep.render_markdown(rep.build_report(make_pool(), included=sample(80, 60, 40)))
    assert "20" in text and "déficit" in text.lower()


def test_write_report_creates_json_and_markdown_in_the_private_work_dir(tmp_path):
    report = rep.build_report(make_pool(), included=sample(1, 1, 1))
    json_path, md_path = rep.write_report(tmp_path, report)
    assert json_path == tmp_path / "data" / "work" / "reports" / "extraction_report.json"
    assert md_path == tmp_path / "data" / "work" / "reports" / "extraction_report.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["funnel"]["included"] == 3
    assert "Relatório" in md_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(os.stat(tmp_path / "data" / "work").st_mode) == 0o700


def test_write_report_is_deterministic(tmp_path):
    report = rep.build_report(make_pool())
    first, _ = rep.write_report(tmp_path, report)
    data = first.read_bytes()
    rep.write_report(tmp_path, report)
    assert first.read_bytes() == data


def _validacao(root, pid, **fields):
    folder = root / "data" / "work" / "problems" / pid
    folder.mkdir(parents=True)
    (folder / "validacao.json").write_text(json.dumps({"problem_id": pid, **fields}))


def test_collect_validation_state_reads_the_problem_folders(tmp_path):
    pool = make_pool((M.MATEMATICA, M.LOGICA_DIRETA, M.LOGICA_DIRETA, M.ESTRUTURAL_OTIMIZACAO))
    ids = sorted(pool.problems)
    _validacao(tmp_path, ids[0], status="complete")
    _validacao(tmp_path, ids[1], status="complete")
    _validacao(
        tmp_path,
        ids[2],
        status="pending_triage",
        triage={"stage": "selection", "verdict": "WA", "reason": "AC diverged"},
    )
    _validacao(tmp_path, ids[3], status="discarded", discard_reason="insufficient_wa")

    state = rep.collect_validation_state(tmp_path, pool)

    assert sorted(state.included) == sorted(
        [pool.problems[ids[0]].macrocategoria, pool.problems[ids[1]].macrocategoria]
    )
    assert state.pending == [
        PendingTriageItem(problem_id=ids[2], stage="selection", reason="AC diverged")
    ]
    assert state.discarded == {"insufficient_wa": 1}


def test_collect_validation_state_without_problems_is_empty(tmp_path):
    state = rep.collect_validation_state(tmp_path, make_pool())
    assert state.included == [] and state.pending == [] and state.discarded == {}


def test_the_selection_is_final_when_the_target_is_reached(tmp_path):
    state = rep.ValidationState(included=sample(80, 60, 60), closed=200)
    assert state.selection_is_final(make_pool())


def test_the_selection_is_final_when_every_pool_problem_is_closed_even_with_a_deficit(tmp_path):
    pool = make_pool((M.MATEMATICA, M.LOGICA_DIRETA, M.LOGICA_DIRETA))
    assert rep.ValidationState(included=[M.MATEMATICA], closed=3).selection_is_final(pool)


def test_the_selection_is_not_final_while_problems_remain_open():
    pool = make_pool((M.MATEMATICA, M.LOGICA_DIRETA, M.LOGICA_DIRETA))
    assert not rep.ValidationState(included=[M.MATEMATICA], closed=2).selection_is_final(pool)


def test_an_empty_pool_is_never_final():
    empty = Pool(
        hf_dataset=config.HF_DATASET,
        hf_revision=config.HF_REVISION,
        seed=config.SEED,
        counts=PoolCounts(funnel={}, rejections={}, eligible=0),
        order=[],
        problems={},
    )
    assert not rep.ValidationState().selection_is_final(empty)


def test_collect_validation_state_counts_the_closed_problems(tmp_path):
    pool = make_pool((M.MATEMATICA, M.LOGICA_DIRETA, M.LOGICA_DIRETA))
    ids = sorted(pool.problems)
    _validacao(tmp_path, ids[0], status="complete")
    _validacao(tmp_path, ids[1], status="discarded", discard_reason="insufficient_wa")
    _validacao(tmp_path, "9999_Z", status="complete")  # not in the pool: ignored
    state = rep.collect_validation_state(tmp_path, pool)
    assert state.closed == 2 and not state.selection_is_final(pool)
