"""`validacao.json` of a problem: how the engine judged its code (data-model.md section 1.3).

The record makes the validation auditable (FR-021a) and carries the triage of an AC that failed in
the engine (FR-011b). Infrastructure failure is never a value here: it is an exception of the
engine (FR-010).
"""

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from dataset import config
from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion, read_in_folder
from sandbox.types import Verdict

MAX_TEXT_BYTES = 64 * 1024
SHA256_PATTERN = r"^[0-9a-f]{64}$"
DiscardReason = Literal["insufficient_wa", "insufficient_raw_wa"]
Group = Literal["public_tests", "private_tests", "generated_tests"]
_STANDARD_FLAG = re.compile(r"^-std=")


def truncate_text(text: str, limit: int = MAX_TEXT_BYTES) -> tuple[str, bool]:
    """Cut ``text`` to ``limit`` UTF-8 bytes without splitting a character; say whether it was cut."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    return data[:limit].decode("utf-8", errors="ignore"), True


def _check_size(value: str | None, what: str) -> str | None:
    if value is not None and len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError(f"{what} is longer than 64 KiB: truncate it and set `truncated`")
    return value


class EngineInfo(Schema):
    """The exact configuration of the engine that produced the verdicts."""

    gcc_version: str
    flags: list[str]  # without `-std`: the standard is recorded per code
    standard_cascade: list[str]
    stack_limit_bytes: int
    time_limit_seconds: float
    memory_limit_bytes: int
    stability_runs: int

    @field_validator("flags")
    @classmethod
    def _no_standard_flag(cls, flags: list[str]) -> list[str]:
        if any(_STANDARD_FLAG.match(flag) for flag in flags):
            raise ValueError("`flags` must not carry `-std`: the standard is recorded per code")
        return flags


class CodeValidation(Schema):
    file: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    verdict: Verdict
    standard_used: str | None
    max_cpu_time_s: float
    max_memory_bytes: int
    tests_run: int


class DecidingTest(Schema):
    group: Group
    index: int = Field(ge=0)


class WaValidation(CodeValidation):
    source_index: int = Field(ge=0)  # position in the dataset's `incorrect_solutions`
    deciding_test: DecidingTest
    stable: bool  # always true in a retained WA


class Divergence(Schema):
    """Where and how the output of an AC differed from the official answer."""

    group: Group
    index: int = Field(ge=0)
    input: str
    expected: str
    actual: str
    truncated: bool
    # Diagnostic of decision D13 (rule 2): equal when compared by whitespace-separated tokens.
    # It NEVER changes a verdict; only the engine's `outputs_equal` decides those.
    format_only: bool

    @field_validator("input", "expected", "actual")
    @classmethod
    def _within_64_kib(cls, value: str) -> str:
        return _check_size(value, "a divergence field")  # type: ignore[return-value]

    @classmethod
    def build(
        cls, group: Group, index: int, *, input_: str, expected: str, actual: str
    ) -> "Divergence":
        cut = [truncate_text(part) for part in (input_, expected, actual)]
        return cls(
            group=group,
            index=index,
            input=cut[0][0],
            expected=cut[1][0],
            actual=cut[2][0],
            truncated=any(flag for _, flag in cut),
            format_only=expected.split() == actual.split(),
        )


class TriageRecord(Schema):
    """An AC that failed in the engine: the problem waits for a manual decision (FR-011b).

    Deterministic on purpose: there is no timestamp.
    """

    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    stage: Literal["selection", "audit"]
    verdict: Literal["WA", "TLE", "MLE", "RE", "CE", "AUDIT_MISMATCH"]
    reason: str
    divergence: Divergence | None
    engine_diagnostic: str | None

    @field_validator("engine_diagnostic")
    @classmethod
    def _diagnostic_within_64_kib(cls, value: str | None) -> str | None:
        return _check_size(value, "the engine diagnostic")


class Validacao(Schema):
    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    status: Literal["complete", "pending_triage", "discarded"]
    engine: EngineInfo
    ac_ref: CodeValidation | None
    wa: list[WaValidation]
    discard_reason: DiscardReason | None
    triage: TriageRecord | None

    @model_validator(mode="after")
    def _invariants(self) -> "Validacao":
        if self.status == "complete":
            self._check_complete()
        elif self.wa:
            raise ValueError("`wa` must be empty unless the problem is complete")
        if (self.status == "discarded") != (self.discard_reason is not None):
            raise ValueError("`discard_reason` is required if discarded and forbidden otherwise")
        if (self.status == "pending_triage") != (self.triage is not None):
            raise ValueError("`triage` is required if pending_triage and forbidden otherwise")
        if self.triage is not None and self.triage.problem_id != self.problem_id:
            raise ValueError("`triage.problem_id` must equal `problem_id`")
        return self

    def _check_complete(self) -> None:
        if len(self.wa) != config.WA_PER_PROBLEM:
            raise ValueError(f"a complete problem has exactly {config.WA_PER_PROBLEM} WA")
        if self.ac_ref is None or self.ac_ref.verdict is not Verdict.AC:
            raise ValueError("a complete problem needs an `ac_ref` with verdict AC")
        for position, item in enumerate(self.wa, start=1):
            if item.verdict is not Verdict.WA:
                raise ValueError(f"WA_{position}.cpp must have the verdict WA")
            if item.file != f"WA_{position}.cpp":
                raise ValueError(f"the file of item {position} must be WA_{position}.cpp")
            if not item.stable:
                raise ValueError(f"WA_{position}.cpp must be stable")
        if len({item.sha256 for item in self.wa}) != len(self.wa):
            raise ValueError("the sha256 of the WA must be distinct (identical texts count once)")

    @classmethod
    def from_folder(cls, folder: Path) -> "Validacao":
        return read_in_folder(cls, folder, "validacao.json")
