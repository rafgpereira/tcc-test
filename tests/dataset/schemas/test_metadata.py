"""Tests for `Metadata` (T052; data-model.md section 1.1, methodology 1.5)."""

import json

import pytest
from pydantic import ValidationError

from dataset.schemas.metadata import Metadata

VALID = {
    "schema_version": 1,
    "problem_id": "1101_A",
    "cf_contest_id": 1101,
    "cf_index": "A",
    "name": "Minimum Integer",
    "source": "CODEFORCES",
    "cf_rating": 1000,
    "cf_points": 500.0,
    "cf_tags": ["math"],
    "macrocategoria": "matematica",
    "time_limit_seconds": 2.0,
    "memory_limit_bytes": 256_000_000,
    "is_description_translated": False,
    "dataset_split_origem": "train",
    "num_wa_brutos_disponiveis": 247,
    "num_wa_validados": 100,
    "extraction_timestamp": "2026-09-18T22:00:00Z",
}


def make(**changes) -> dict:
    return {**VALID, **changes}


def test_a_valid_metadata_is_accepted():
    assert Metadata.model_validate(VALID).problem_id == "1101_A"


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"problem_id": "not-an-id"},
        {"problem_id": "1101"},
        {"problem_id": "A_1101"},
        {"cf_contest_id": 0},
        {"cf_contest_id": -3},
        {"cf_index": ""},
        {"name": ""},
        {"source": "ATCODER"},
        {"cf_rating": 999},
        {"cf_rating": 1601},
        {"cf_points": -1.0},
        {"time_limit_seconds": 0},
        {"time_limit_seconds": -1.5},
        {"memory_limit_bytes": 0},
        {"is_description_translated": True},
        {"dataset_split_origem": "dev"},
        {"num_wa_brutos_disponiveis": 99},
        {"num_wa_validados": 99},
        {"num_wa_validados": 101},
        {"extraction_timestamp": "2026-09-18"},
        {"extraction_timestamp": "18/09/2026 22:00"},
        {"extraction_timestamp": ""},
    ],
)
def test_each_constraint_is_rejected_verbatim(changes):
    with pytest.raises(ValidationError):
        Metadata.model_validate(make(**changes))


@pytest.mark.parametrize("rating", [1000, 1300, 1600])
def test_the_rating_boundaries_are_inclusive(rating):
    assert Metadata.model_validate(make(cf_rating=rating)).cf_rating == rating


def test_the_number_of_raw_wa_can_be_exactly_100():
    assert Metadata.model_validate(make(num_wa_brutos_disponiveis=100))


def test_the_tags_are_sorted_alphabetically_when_written():
    meta = Metadata.model_validate(
        make(cf_tags=["strings", "math", "implementation"], macrocategoria="matematica")
    )
    assert meta.cf_tags == ["implementation", "math", "strings"]
    assert json.loads(meta.model_dump_json())["cf_tags"] == ["implementation", "math", "strings"]


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        (["math"], "matematica"),
        (["implementation", "strings"], "logica_direta"),
        (["math", "dp"], "estrutural_otimizacao"),  # structural wins over math
        (["math", "implementation"], "matematica"),  # math wins over direct logic
    ],
)
def test_the_category_must_be_the_classification_of_the_tags(tags, category):
    assert Metadata.model_validate(make(cf_tags=tags, macrocategoria=category))


def test_a_category_that_disagrees_with_the_tags_is_rejected():
    with pytest.raises(ValidationError, match="macrocategoria"):
        Metadata.model_validate(make(cf_tags=["math"], macrocategoria="logica_direta"))


def test_tags_without_any_allowed_tag_are_rejected():
    with pytest.raises(ValidationError):
        Metadata.model_validate(make(cf_tags=["geometry"], macrocategoria="matematica"))


def test_unknown_fields_are_errors():
    with pytest.raises(ValidationError):
        Metadata.model_validate(make(surprise=1))


def test_metadata_keeps_the_portuguese_keys_of_the_methodology():
    keys = set(Metadata.model_validate(VALID).model_dump())
    assert {"macrocategoria", "dataset_split_origem", "num_wa_validados"} <= keys
    assert {"num_wa_brutos_disponiveis", "extraction_timestamp"} <= keys


def test_the_problem_id_must_equal_the_folder_name(tmp_path):
    folder = tmp_path / "1101_A"
    folder.mkdir()
    (folder / "metadata.json").write_text(json.dumps(VALID))
    assert Metadata.from_folder(folder).problem_id == "1101_A"
    other = tmp_path / "9999_Z"
    other.mkdir()
    (other / "metadata.json").write_text(json.dumps(VALID))
    with pytest.raises(ValueError, match="folder"):
        Metadata.from_folder(other)
