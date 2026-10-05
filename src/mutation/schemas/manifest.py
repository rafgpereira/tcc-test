"""Schema of the integrity manifest of the mutants zip (data-model.md, "Pacote de mutantes").

Same shape as ``manifests/dataset.manifest.json`` (Constitution, Principle IV): the hash and size
of the zip itself and of every file inside it, ordered by path.
"""

import re

from pydantic import model_validator

from dataset.schemas.common import Schema, SchemaVersion
from dataset.schemas.manifest import FileHash

MUTANT_PATH = re.compile(r"^mutants/problems/\d+_[A-Za-z0-9]+/Mutant_[1-9]\d*\.cpp$")

__all__ = ["FileHash", "Manifest"]


class Manifest(Schema):
    schema_version: SchemaVersion = 1
    mutants_zip: FileHash
    files: list[FileHash]  # one per file inside the zip, `path` as inside the zip, sorted

    @model_validator(mode="after")
    def _zip_path_is_fixed(self) -> "Manifest":
        if self.mutants_zip.path != "data/mutants.zip":
            raise ValueError('mutants_zip.path must be "data/mutants.zip"')
        return self

    @model_validator(mode="after")
    def _files_are_sorted_by_path(self) -> "Manifest":
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("files must be ordered by path")
        return self

    @model_validator(mode="after")
    def _files_are_mutants(self) -> "Manifest":
        for item in self.files:
            if not MUTANT_PATH.match(item.path):
                raise ValueError(
                    f"{item.path!r} is not mutants/problems/<id>/Mutant_<n>.cpp: only mutant files "
                    "are packaged"
                )
        return self
