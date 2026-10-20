"""The schemas of revision 2 (data-model.md §1 to §3) and the manifest of a revision."""

import pytest
from pydantic import ValidationError

from dataset.schemas.manifest import Manifest, RevisedManifest, parse_manifest
from dataset.schemas.revision import ChangedStatement, DatasetRevision, StatementDecision

SHA = "a" * 64


def decision(**kw):
    data = dict(
        problem_id="1_A",
        decision="correct",
        enunciado="x",
        reason="r",
        reviewed_by="M",
        reviewed_at="2026-10-18",
        sha256_before=SHA,
    )
    data.update(kw)
    return StatementDecision(**data)


def test_a_decision_has_a_text_exactly_when_it_corrects():
    decision()
    decision(decision="keep", enunciado=None)
    with pytest.raises(ValidationError):
        decision(decision="keep")
    with pytest.raises(ValidationError):
        decision(enunciado=None)
    with pytest.raises(ValidationError):
        decision(reason=" ")
    draft = decision(decision=None, enunciado=None, reason="", reviewed_by="", reviewed_at="")
    assert draft.is_draft


def changed(pid, origin="automatic", **kw):
    return ChangedStatement(
        problem_id=pid, origin=origin, sha256_before=SHA, sha256_after=SHA, **kw
    )


def test_changed_and_kept_are_disjoint_and_sorted():
    DatasetRevision(
        revision=2,
        previous_manifest_sha256=SHA,
        changed=[changed("1_A"), changed("2_B", "manual", reason="r")],
        kept=[],
    )
    with pytest.raises(ValidationError):
        DatasetRevision(
            revision=2,
            previous_manifest_sha256=SHA,
            changed=[changed("1_A")],
            kept=[{"problem_id": "1_A", "reason": "r"}],
        )
    with pytest.raises(ValidationError):
        changed("1_A", "manual")  # a manual change has its reason


MANIFEST = {
    "schema_version": 1,
    "dataset_zip": {"path": "data/dataset.zip", "size": 1, "sha256": SHA},
    "files": [{"path": "dataset/problems/1_A/enunciado.md", "size": 1, "sha256": SHA}],
    "problem_count": 1,
    "provenance": {"hf_dataset": "d", "hf_revision": "r", "seed": 42},
}
REVISION_OF = {
    "previous_manifest_sha256": SHA,
    "fidelity_report_sha256": SHA,
    "originals_manifest_sha256": SHA,
    "revision_record_sha256": SHA,
    "created_at": "2026-10-18T00:00:00Z",
}


def test_parse_manifest_reads_both_versions():
    assert type(parse_manifest(MANIFEST)) is Manifest
    revised = parse_manifest(
        {**MANIFEST, "schema_version": 2, "revision": 2, "revision_of": REVISION_OF}
    )
    assert isinstance(revised, RevisedManifest) and revised.revision == 2
    with pytest.raises(ValidationError):
        parse_manifest({**MANIFEST, "schema_version": 2, "revision": 1, "revision_of": REVISION_OF})
    with pytest.raises(ValidationError):
        parse_manifest({**MANIFEST, "revision": 2})  # version 1 has no revision
