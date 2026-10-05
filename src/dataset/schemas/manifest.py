"""Schema of the integrity manifest (spec FR-027; data-model.md §1.5)."""

from pydantic import model_validator

from dataset.schemas.common import Schema, SchemaVersion
from dataset.schemas.report import Provenance


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
