"""`testes.json` of a problem: the official suite in execution order (data-model.md section 1.2)."""

from collections.abc import Sequence
from pathlib import Path

from pydantic import Field, model_validator

from dataset.schemas.common import PROBLEM_ID_PATTERN, Schema, SchemaVersion, read_in_folder


class TestCase(Schema):
    __test__ = False  # not a pytest test class

    input: str
    output: str


class Testes(Schema):
    """The suite runs public tests, then private tests, then generated tests (FR-012)."""

    __test__ = False  # not a pytest test class

    schema_version: SchemaVersion = 1
    problem_id: str = Field(pattern=PROBLEM_ID_PATTERN)
    public_tests: list[TestCase]
    private_tests: list[TestCase]
    generated_tests: list[TestCase]

    @model_validator(mode="after")
    def _at_least_one_test(self) -> "Testes":
        if not (self.public_tests or self.private_tests or self.generated_tests):
            raise ValueError("a problem needs at least one test in total")
        return self

    @classmethod
    def from_parallel_lists(
        cls,
        problem_id: str,
        *,
        public: tuple[Sequence[str], Sequence[str]],
        private: tuple[Sequence[str], Sequence[str]],
        generated: tuple[Sequence[str], Sequence[str]],
    ) -> "Testes":
        """Build from the dataset's ``(inputs, outputs)`` lists; different lengths are an error."""

        def zip_group(name: str, group: tuple[Sequence[str], Sequence[str]]) -> list[TestCase]:
            inputs, outputs = group
            if len(inputs) != len(outputs):
                raise ValueError(f"{name}: `input` and `output` must have the same length")
            return [TestCase(input=i, output=o) for i, o in zip(inputs, outputs, strict=True)]

        return cls(
            problem_id=problem_id,
            public_tests=zip_group("public_tests", public),
            private_tests=zip_group("private_tests", private),
            generated_tests=zip_group("generated_tests", generated),
        )

    @classmethod
    def from_folder(cls, folder: Path) -> "Testes":
        return read_in_folder(cls, folder, "testes.json")
