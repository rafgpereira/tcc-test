"""``python -m dataset revise``: revision 2 of the dataset (specs/007, research R2 to R5)."""

import json
import zipfile

import pytest

from dataset import __main__ as cli
from dataset import config, revision
from dataset.schemas.manifest import RevisedManifest, parse_manifest
from dataset.schemas.revision import DatasetRevision, StatementDecision
from tests.ai_clients.conftest import build_dataset, problem
from tests.dataset.statements.conftest import FakeClock, path_of
from tests.dataset.statements.fixtures import (
    NEW_LEGEND_HTML,
    NEW_LEGEND_OURS,
    OLD_LEGEND_HTML,
    OLD_LEGEND_OURS,
    enunciado,
    page,
)

# 1_A: lost exponent and index (automatic); 2_B: faithful; 3_C: a changed word (review).
LEGENDS = {
    "1_A": (OLD_LEGEND_HTML, OLD_LEGEND_OURS),
    "2_B": (NEW_LEGEND_HTML, NEW_LEGEND_OURS),
    "3_C": (
        'The cat sleeps 10<sup class="upper-index">9</sup> hours.',
        "The dog sleeps 109 hours.",
    ),
}


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(cli, "make_statements_clock", FakeClock)


@pytest.fixture()
def checked(tmp_path, monkeypatch, site):
    """A dataset of 3 problems and its fidelity report (check-statements against a local site)."""
    files = {}
    for pid, (legend_html, legend_ours) in LEGENDS.items():
        files[pid] = problem(pid)
        files[pid]["enunciado.md"] = enunciado(legend_ours)
        site.pages[path_of(pid)] = [(200, page(legend_html).encode())]
    root = build_dataset(tmp_path, files)
    monkeypatch.chdir(root)
    assert cli.main(["check-statements"]) == cli.EXIT_OK
    return root


def decide(root, pid, **kw):
    path = revision.decision_path(root, pid)
    data = json.loads(path.read_text())
    data.update(kw)
    path.write_text(json.dumps(data))


def snapshot(root):
    paths = [root / config.DATASET_ZIP, root / config.MANIFEST_PATH, root / "data/dataset"]
    out = []
    for p in paths:
        for f in [p] if p.is_file() else sorted(p.rglob("*")):
            if f.is_file():
                out.append((str(f), f.read_bytes()))
    return out


def test_drafts_bring_the_differences_and_the_suggested_marks(checked, capsys):
    assert cli.main(["revise", "--draft-decisions"]) == cli.EXIT_OK
    draft = StatementDecision.model_validate_json(
        revision.decision_path(checked, "3_C").read_bytes()
    )
    assert draft.is_draft and {d.kind for d in draft.differences} == {"other", "lost_exponent"}
    assert "10^{9}" in draft.suggested_enunciado and "dog" in draft.suggested_enunciado
    assert not revision.decision_path(checked, "1_A").exists()  # automatic, no decision
    decide(checked, "3_C", reason="kept")
    capsys.readouterr()
    assert cli.main(["revise", "--draft-decisions"]) == cli.EXIT_OK  # never overwrites
    assert json.loads(revision.decision_path(checked, "3_C").read_text())["reason"] == "kept"


def test_without_the_decisions_nothing_is_written(checked, capsys):
    before = snapshot(checked)
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "no decision yet for 1 problem(s) under review: 3_C" in capsys.readouterr().err
    assert snapshot(checked) == before


def correct_3c(root):
    cli.main(["revise", "--draft-decisions"])
    text = revision._read_enunciado(root, "3_C").replace("dog sleeps 109", "cat sleeps 10^{9}")
    decide(
        root,
        "3_C",
        decision="correct",
        enunciado=text,
        reason="the original says cat",
        reviewed_by="Milena",
        reviewed_at="2026-10-18",
    )


def test_revision_2_changes_only_the_statements_and_keeps_revision_1(checked, capsys):
    correct_3c(checked)
    rev1_zip = (checked / config.DATASET_ZIP).read_bytes()
    rev1_manifest = (checked / config.MANIFEST_PATH).read_bytes()
    assert cli.main(["revise", "--dry-run"]) == cli.EXIT_OK
    assert (checked / config.DATASET_ZIP).read_bytes() == rev1_zip  # dry run: nothing written
    capsys.readouterr()
    assert cli.main(["revise"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "revision 2: 2 statements changed (1 automatic, 1 manual), 0 kept, 1 unchanged" in out
    assert "--problem 1_A --problem 3_C --scenario black_box --scenario hybrid" in out
    assert (checked / config.REVISION1_ZIP).read_bytes() == rev1_zip
    assert (checked / config.REVISION1_MANIFEST).read_bytes() == rev1_manifest
    manifest = parse_manifest((checked / config.MANIFEST_PATH).read_bytes())
    assert isinstance(manifest, RevisedManifest) and manifest.revision == 2
    record = DatasetRevision.model_validate_json((checked / config.REVISION_RECORD).read_bytes())
    assert [(c.problem_id, c.origin) for c in record.changed] == [
        ("1_A", "automatic"),
        ("3_C", "manual"),
    ]
    old = {f.path: f.sha256 for f in parse_manifest(rev1_manifest).files}
    new = {f.path: f.sha256 for f in manifest.files}
    assert {p for p in old if old[p] != new[p]} == {
        "dataset/problems/1_A/enunciado.md",
        "dataset/problems/3_C/enunciado.md",
    }
    with zipfile.ZipFile(checked / config.DATASET_ZIP) as zf:
        text = zf.read("dataset/problems/1_A/enunciado.md").decode()
    assert "10^{5}" in text and "a_{i}" in text
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE  # revision 2 already exists


def test_the_same_inputs_give_the_same_zip(checked, tmp_path):
    correct_3c(checked)
    first = revision.build_revision(checked, dry_run=True, now="2026-10-18T00:00:00Z")
    second = revision.build_revision(checked, dry_run=True, now="2026-10-18T00:00:00Z")
    assert first.manifest == second.manifest


def test_a_decision_that_changes_other_text_is_refused(checked, capsys):
    cli.main(["revise", "--draft-decisions"])
    text = revision._read_enunciado(checked, "3_C").replace("One line.", "Two lines.")
    decide(
        checked,
        "3_C",
        decision="correct",
        enunciado=text,
        reason="r",
        reviewed_by="M",
        reviewed_at="2026-10-18",
    )
    capsys.readouterr()
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "changes text the report did not find different" in capsys.readouterr().err


def test_a_decision_about_another_text_or_problem_is_refused(checked, capsys):
    cli.main(["revise", "--draft-decisions"])
    decide(
        checked,
        "3_C",
        decision="keep",
        reason="r",
        reviewed_by="M",
        reviewed_at="d",
        sha256_before="0" * 64,
    )
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "sha256_before" in capsys.readouterr().err
    stray = revision.decision_path(checked, "2_B")
    stray.write_text(revision.decision_path(checked, "3_C").read_text())
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "not under review: 2_B" in capsys.readouterr().err


def test_a_report_of_another_dataset_or_a_changed_dataset_is_refused(checked, capsys):
    correct_3c(checked)
    path = checked / config.STATEMENT_FIDELITY_REPORT
    data = json.loads(path.read_text())
    data["dataset_manifest_sha256"] = "b" * 64
    path.write_text(json.dumps(data))
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "another dataset" in capsys.readouterr().err
    (checked / "data/dataset/problems/2_B/AC_ref.cpp").write_text("changed")
    assert cli.main(["revise"]) == cli.EXIT_DATA_FAILURE
    assert "does not match" in capsys.readouterr().err


def test_keep_leaves_the_statement_as_it_is(checked, capsys):
    cli.main(["revise", "--draft-decisions"])
    decide(
        checked,
        "3_C",
        decision="keep",
        reason="the page changed",
        reviewed_by="M",
        reviewed_at="2026-10-18",
    )
    assert cli.main(["revise"]) == cli.EXIT_OK
    record = DatasetRevision.model_validate_json((checked / config.REVISION_RECORD).read_bytes())
    assert [k.problem_id for k in record.kept] == ["3_C"] and len(record.changed) == 1


def test_differences_close_together_are_one_stretch():
    from types import SimpleNamespace

    text = "aaaa BBB cc DDD eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee FFF."
    diffs = [SimpleNamespace(ours_offset=text.index(w), ours_length=3) for w in ("BBB", "DDD")]
    fidelity = SimpleNamespace(differences=diffs)

    def decision(new):
        return StatementDecision(
            problem_id="1_A",
            decision="correct",
            enunciado=new,
            reason="r",
            reviewed_by="M",
            reviewed_at="2026-10-18",
            sha256_before=revision._sha(text),
        )

    revision.check_decision(
        text, decision(text.replace("BBB cc DDD", "a whole new phrase")), fidelity
    )
    with pytest.raises(revision.RevisionRefused):  # far from any difference
        revision.check_decision(text, decision(text.replace("FFF", "GGG")), fidelity)
