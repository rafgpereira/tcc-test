"""The official suite of a problem, in execution order (FR-012).

Public tests run first, then private tests, then generated tests (D1); the FIRST test that is not
AC decides the verdict. Each test remembers the group and the index inside the group it came from,
which is what `validacao.json` and the triage records report.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from dataset.schemas.pool import RawProblem
from dataset.schemas.testes import Testes
from sandbox.types import Test

GROUPS = ("public_tests", "private_tests", "generated_tests")


@dataclass(frozen=True)
class Suite:
    tests: tuple[Test, ...]
    locations: tuple[tuple[str, int], ...]  # (group, index inside the group), aligned with tests

    def location(self, deciding_index: int) -> tuple[str, int]:
        return self.locations[deciding_index]


def _build(groups: Iterable[tuple[str, Sequence[tuple[str, str]]]]) -> Suite:
    tests: list[Test] = []
    locations: list[tuple[str, int]] = []
    for name, cases in groups:
        for index, (given, expected) in enumerate(cases):
            tests.append(Test(given, expected))
            locations.append((name, index))
    return Suite(tuple(tests), tuple(locations))


def suite_from_raw(raw: RawProblem) -> Suite:
    return _build(
        (name, list(zip(group.input, group.output, strict=True)))
        for name in GROUPS
        for group in [getattr(raw, name)]
    )


def suite_from_testes(testes: Testes) -> Suite:
    return _build(
        (name, [(case.input, case.output) for case in getattr(testes, name)]) for name in GROUPS
    )
