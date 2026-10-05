"""Tests for the shared types of the mutation module (data-model.md; contracts/mutation-api.md)."""

import dataclasses

import pytest

from mutation.types import (
    DiscardReason,
    MutationOperator,
    Site,
    SiteKind,
    Verdict,
)


def _site(**overrides) -> Site:
    fields = dict(
        kind=SiteKind.OPERATOR,
        node_type="binary_expression",
        start_byte=10,
        end_byte=11,
        discovery_index=0,
        eligible_operators=(MutationOperator.ROR,),
    )
    fields.update(overrides)
    return Site(**fields)


def test_mutation_operator_has_exactly_the_five_offutt_operators():
    assert [m.name for m in MutationOperator] == ["ROR", "AOR", "LCR", "ABS", "UOI"]


def test_discard_reason_has_exactly_the_seven_reasons_of_the_funnel():
    assert {m.name for m in DiscardReason} == {
        "DUPLICATE",
        "COMPILE_ERROR",
        "TLE",
        "MLE",
        "RE",
        "EQUIVALENT",
        "UNSTABLE",
    }
    assert len(DiscardReason) == 7


def test_site_kind_has_exactly_operator_and_the_two_operands():
    assert {m.name for m in SiteKind} == {"OPERATOR", "OPERAND_LEFT", "OPERAND_RIGHT"}


def test_site_is_frozen():
    site = _site()
    with pytest.raises(dataclasses.FrozenInstanceError):
        site.start_byte = 99  # type: ignore[misc]


def test_site_is_comparable_by_node_type_range_and_kind_only():
    a = _site(discovery_index=0, eligible_operators=(MutationOperator.ROR,))
    b = _site(discovery_index=7, eligible_operators=(MutationOperator.AOR,))
    assert a == b and hash(a) == hash(b)  # discovery order and operators are not identity
    assert a != _site(start_byte=11)
    assert a != _site(end_byte=12)
    assert a != _site(node_type="update_expression")
    assert a != _site(kind=SiteKind.OPERAND_LEFT)


def test_site_is_usable_as_a_dictionary_key():
    assert {_site(): 1}[_site(discovery_index=3)] == 1


def test_verdict_is_the_engine_verdict_reexported():
    from sandbox.types import Verdict as EngineVerdict

    assert Verdict is EngineVerdict
