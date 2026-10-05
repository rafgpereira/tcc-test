"""Shared types of the mutation module (contracts/mutation-api.md; data-model.md).

Everything here is immutable: a site, a candidate or a mutant never changes after it is built, so
the deterministic order of the module cannot be disturbed by a later mutation of a shared object.
"""

from dataclasses import dataclass, field
from enum import Enum

from sandbox.types import Verdict

__all__ = [
    "DiscardReason",
    "DiscardRecord",
    "ExclusionAlert",
    "Mutant",
    "MutantCandidate",
    "MutationOperator",
    "Selection",
    "Site",
    "SiteKind",
    "ValidationOutcome",
    "Verdict",
]


class MutationOperator(str, Enum):
    """The operators of Offutt et al. (1996) adopted by the experiment (decision D2)."""

    ROR = "ROR"  # relational operator replacement
    AOR = "AOR"  # arithmetic operator replacement
    LCR = "LCR"  # logical connector replacement
    ABS = "ABS"  # absolute value insertion
    UOI = "UOI"  # unary operator insertion


class DiscardReason(str, Enum):
    """Why a candidate did not become a mutant (spec FR-005 and FR-007)."""

    DUPLICATE = "duplicate"
    COMPILE_ERROR = "compile_error"
    TLE = "tle"
    MLE = "mle"
    RE = "re"
    EQUIVALENT = "equivalent"
    UNSTABLE = "unstable"


class SiteKind(str, Enum):
    """Which part of the syntax node a site occupies."""

    OPERATOR = "OPERATOR"
    OPERAND_LEFT = "OPERAND_LEFT"
    OPERAND_RIGHT = "OPERAND_RIGHT"


@dataclass(frozen=True)
class Site:
    """A place of ``AC_ref.cpp`` a mutation operator can change.

    Two sites are the same site when they cover the same bytes of the same kind of node in the same
    role; the discovery order and the operators are properties of the site, not part of its
    identity.
    """

    kind: SiteKind
    node_type: str  # binary_expression | unary_expression | update_expression
    start_byte: int  # UTF-8 byte range of the text the operators replace
    end_byte: int
    discovery_index: int = field(compare=False)  # position in the pre-order walk (research R3)
    eligible_operators: tuple[MutationOperator, ...] = field(compare=False)
    # Operator token of the binary expression an operand belongs to (None for operator sites);
    # decides which unary operators are legal in front of the operand.
    parent_operator: str | None = field(default=None, compare=False)
    # Node type of the operand (None for operator sites): ``++``/``--`` only go in front of
    # something that can be an lvalue.
    operand_type: str | None = field(default=None, compare=False)


@dataclass(frozen=True)
class MutantCandidate:
    """A mutated text that has not been validated yet."""

    problem_id: str
    sites: tuple[Site, ...]  # 1 site (first order), 2 (pair) or 3 (triple)
    operators: tuple[tuple[MutationOperator, int], ...]  # (operator, variant) per site
    source: str

    @property
    def order(self) -> int:
        return len(self.sites)


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of validating a candidate: a verdict (kept) or a reason (discarded), never both."""

    verdict: Verdict | None = None
    discard_reason: DiscardReason | None = None
    deciding_index: int | None = None  # index of the test that decided the verdict

    def __post_init__(self) -> None:
        if (self.verdict is None) == (self.discard_reason is None):
            raise ValueError("exactly one of `verdict` and `discard_reason` must be set")

    @property
    def accepted(self) -> bool:
        return self.discard_reason is None


@dataclass(frozen=True)
class Mutant:
    """A validated mutant, ready to be persisted as ``Mutant_<index>.cpp``."""

    problem_id: str
    index: int  # 1..100, in the order of acceptance
    order: int  # 1, 2 or 3
    sites: tuple[Site, ...]
    operators: tuple[tuple[MutationOperator, int], ...]
    source: str
    source_sha256: str
    verdict: Verdict
    stability_runs: int


@dataclass(frozen=True)
class DiscardRecord:
    problem_id: str
    order: int
    reason: DiscardReason


@dataclass(frozen=True)
class ExclusionAlert:
    """The problem could not reach 100 mutants and is left out of the mutation score (FR-009)."""

    problem_id: str
    mutants_reached: int
    highest_order_attempted: int


@dataclass(frozen=True)
class Selection:
    """What the mutation of one problem ended in: the mutants (or an alert) and every discard."""

    mutants: tuple[Mutant, ...]
    alert: ExclusionAlert | None
    discards: tuple[DiscardRecord, ...]
