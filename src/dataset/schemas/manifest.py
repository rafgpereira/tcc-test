"""Schema of the integrity manifest (spec FR-027; data-model.md §1.5).

``schema_version`` 1 is the dataset as first extracted and validated (revision 1). ``schema_version``
2 is a numbered revision (constitution 1.8.0, specs/007): the same fields plus ``revision`` and
``revision_of``, its provenance, which never enters a hash. ``parse_manifest`` reads either.
"""

import json
from typing import Literal

from pydantic import Field, model_validator

from dataset.schemas.common import Schema, SchemaVersion
from dataset.schemas.report import Provenance

_SHA = r"^[0-9a-f]{64}$"


class FileHash(Schema):
    path: str
    size: int
    sha256: str


class Manifest(Schema):
    schema_version: SchemaVersion = 1
    dataset_zip: FileHash
    files: list[FileHash]  # one per file inside the zip, `path` relative to its root, sorted
    problem_count: int
    provenance: Provenance  # traceability only; never enters a hash

    @model_validator(mode="after")
    def _dataset_zip_path_is_fixed(self) -> "Manifest":
        if self.dataset_zip.path != "data/dataset.zip":
            raise ValueError('dataset_zip.path must be "data/dataset.zip"')
        return self

    @model_validator(mode="after")
    def _files_are_sorted_by_path(self) -> "Manifest":
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("files must be ordered by path")
        return self

    @model_validator(mode="after")
    def _problem_count_matches_the_files(self) -> "Manifest":
        # every file lives under "dataset/problems/<problem_id>/..."; count the distinct ids
        ids = set()
        for item in self.files:
            parts = item.path.split("/")
            if len(parts) >= 3 and parts[0] == "dataset" and parts[1] == "problems":
                ids.add(parts[2])
        if self.problem_count != len(ids):
            raise ValueError(
                f"problem_count ({self.problem_count}) must equal the number of problem "
                f"folders found in files ({len(ids)})"
            )
        return self


class RevisionOf(Schema):
    """Where a revision came from (traceability only; never enters a hash)."""

    previous_manifest_sha256: str = Field(pattern=_SHA)
    fidelity_report_sha256: str = Field(pattern=_SHA)
    originals_manifest_sha256: str = Field(pattern=_SHA)
    revision_record_sha256: str = Field(pattern=_SHA)
    created_at: str


class RevisedManifest(Manifest):
    """The manifest of a numbered revision of the dataset (``schema_version`` 2)."""

    schema_version: Literal[2] = 2
    revision: int = Field(ge=2)
    revision_of: RevisionOf


def parse_manifest(raw: str | bytes | dict) -> Manifest:
    """The manifest of either version: a revision (2) or the first one (1)."""
    data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    if data.get("schema_version") == 2:
        return RevisedManifest.model_validate(data)
    return Manifest.model_validate(data)
