"""``manifests/evaluation_<set>_report.json`` and the manifest of the package (data-model.md)."""

import re

from pydantic import Field, model_validator

from dataset.schemas.common import Schema, SchemaVersion
from dataset.schemas.manifest import FileHash
from evaluation.schemas.result import SetName


class EvaluationReport(Schema):
    schema_version: SchemaVersion = 1
    set: SetName
    run_sha256: str
    complete: bool
    missing: list[str]  # "<problem> <scenario>" without a result, or problems with partial targets
    problems: int = Field(ge=0)
    combinations: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    without_suite: dict[str, int]  # by reason
    ac_approved: int = Field(ge=0)
    ac_rejected: int = Field(ge=0)
    ac_tests: dict[str, int]  # by final verdict: passed, wrong_output, runtime_error
    ac_errors: dict[str, int]  # runtime_error tests by kind: RE, TLE, MLE
    ac_unstable_tests: int = Field(ge=0)
    target_unstable_tests: dict[str, int]  # by kind of target: wa, mutant
    detected: dict[str, int]  # declared_wa, declared_mutants, corrected_wa, corrected_mutants
    corrected_oracle_excluded_tests: int = Field(ge=0)
    targets_not_compiled: list[str]  # "<problem> <scenario> <target>"
    largest_ac_output_bytes: int = Field(ge=0)
    elapsed_s: float = Field(ge=0)  # running the tests; the compilation is per problem, apart


class EvaluationManifest(Schema):
    schema_version: SchemaVersion = 1
    set: SetName
    evaluation_zip: FileHash
    files: list[FileHash]  # one per file inside the zip, `path` as inside the zip, sorted

    @model_validator(mode="after")
    def _well_formed(self) -> "EvaluationManifest":
        if self.evaluation_zip.path != f"data/evaluation_{self.set}.zip":
            raise ValueError(f'evaluation_zip.path must be "data/evaluation_{self.set}.zip"')
        paths = [item.path for item in self.files]
        if paths != sorted(paths):
            raise ValueError("files must be ordered by path")
        prefix = re.escape(f"evaluation/{self.set}/")
        pattern = re.compile(
            rf"^{prefix}(run\.json|results\.csv|problems/\d+_[A-Za-z0-9]+/"
            r"(black_box|white_box|hybrid)\.json)$"
        )
        for path in paths:
            if not pattern.match(path):
                raise ValueError(f"{path!r} is not a file of the evaluation set {self.set}")
        return self
