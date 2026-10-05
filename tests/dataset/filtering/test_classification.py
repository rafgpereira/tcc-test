"""Tests for the macro-category rule and its fixed priority (T023; FR-006, FR-007)."""

import itertools

import pytest

from dataset.filtering.classification import classify
from dataset.schemas.common import Macrocategoria as M


@pytest.mark.parametrize(
    "tags, expected",
    [
        (["math", "implementation"], M.MATEMATICA),
        (["dp", "math"], M.ESTRUTURAL_OTIMIZACAO),
        (["binary search", "sortings", "implementation"], M.ESTRUTURAL_OTIMIZACAO),
        (["greedy", "strings"], M.LOGICA_DIRETA),
        (["dp", "greedy"], M.ESTRUTURAL_OTIMIZACAO),
    ],
)
def test_the_five_examples_of_the_methodology(tags, expected):
    assert classify(tags) is expected


@pytest.mark.parametrize("tag", ["dp", "binary search", "sortings"])
def test_each_structural_tag_wins_over_everything(tag):
    assert classify([tag, "math", "implementation", "strings", "greedy"]) is M.ESTRUTURAL_OTIMIZACAO


def test_math_wins_over_the_direct_logic_tags():
    assert classify(["math", "implementation", "strings", "greedy"]) is M.MATEMATICA


@pytest.mark.parametrize("tag", ["implementation", "strings", "greedy"])
def test_direct_logic_tags_alone(tag):
    assert classify([tag]) is M.LOGICA_DIRETA


def test_the_result_does_not_depend_on_the_order_of_the_tags():
    tags = ["greedy", "math", "implementation", "dp"]
    results = {classify(list(p)) for p in itertools.permutations(tags)}
    assert results == {M.ESTRUTURAL_OTIMIZACAO}
    tags = ["math", "strings", "greedy"]
    assert {classify(list(p)) for p in itertools.permutations(tags)} == {M.MATEMATICA}


def test_tags_outside_the_allowed_list_are_ignored():
    assert classify(["number theory", "greedy"]) is M.LOGICA_DIRETA
    assert classify(["number theory", "brute force", "math"]) is M.MATEMATICA
    assert classify(["combinatorics", "dp"]) is M.ESTRUTURAL_OTIMIZACAO


def test_a_tag_set_with_no_allowed_tag_has_no_category():
    """Such a problem is already ineligible; the classifier refuses to invent a category."""
    with pytest.raises(ValueError):
        classify(["number theory"])
    with pytest.raises(ValueError):
        classify([])


def test_the_category_values_are_exactly_the_documented_ones():
    assert {m.value for m in M} == {"matematica", "estrutural_otimizacao", "logica_direta"}
