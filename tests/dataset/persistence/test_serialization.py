"""Tests for deterministic serialization and atomic writes (T012, part 1)."""

import json
import os

import pytest
from pydantic import BaseModel

from dataset.persistence import store


class Item(BaseModel):
    b: int
    a: str


def test_json_format_is_sorted_indented_utf8_with_final_newline(tmp_path):
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"b": 1, "a": "ção"})
    raw = target.read_bytes()
    assert raw == '{\n  "a": "ção",\n  "b": 1\n}\n'.encode()
    assert not raw.startswith(b"\xef\xbb\xbf"), "no BOM"
    assert b"\r" not in raw


def test_same_object_gives_identical_bytes_regardless_of_key_order(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    store.atomic_write_json(a, {"x": 1, "y": [3, 2, 1], "z": {"k": 1, "j": 2}})
    store.atomic_write_json(b, {"z": {"j": 2, "k": 1}, "y": [3, 2, 1], "x": 1})
    assert a.read_bytes() == b.read_bytes()
    store.atomic_write_json(a, {"x": 1, "y": [3, 2, 1], "z": {"k": 1, "j": 2}})
    assert a.read_bytes() == b.read_bytes()


def test_pydantic_models_are_serialized_like_dicts(tmp_path):
    target = tmp_path / "m.json"
    store.atomic_write_json(target, Item(b=2, a="é"))
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": "é", "b": 2}


def test_failed_serialization_leaves_no_partial_or_temp_file(tmp_path):
    target = tmp_path / "x.json"
    with pytest.raises(TypeError):
        store.atomic_write_json(target, {"bad": {1, 2}})  # a set is not JSON serializable
    assert list(tmp_path.iterdir()) == []


def test_failed_write_preserves_the_previous_content(tmp_path):
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"v": 1})
    before = target.read_bytes()
    with pytest.raises(TypeError):
        store.atomic_write_json(target, {"bad": object()})
    assert target.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_replace_failure_removes_the_temp_file_and_keeps_the_original(tmp_path, monkeypatch):
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"v": 1})
    before = target.read_bytes()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.atomic_write_json(target, {"v": 2})
    monkeypatch.undo()
    assert target.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_text_normalization_only_changes_encoding_and_crlf():
    assert store.normalize_text("a\r\nb\r\n") == "a\nb\n"
    assert store.normalize_text("a\nb") == "a\nb"
    assert store.normalize_text("é ã ç") == "é ã ç"
    assert store.normalize_text(b"a\r\n\xc3\xa9") == "a\né"
    assert store.normalize_text(b"\xef\xbb\xbfint main(){}") == "int main(){}", "BOM removed"
    assert store.normalize_text(b"caf\xe9", encoding="latin-1") == "café"
    assert store.normalize_text(b"caf\xe9") == "caf�", "invalid UTF-8 is replaced, not raised"
    assert store.normalize_text("a\rb") == "a\rb", "a lone CR is not touched"


def test_atomic_write_text_normalizes_and_is_atomic(tmp_path):
    target = tmp_path / "AC_ref.cpp"
    store.atomic_write_text(target, "int main() {\r\n  return 0;\r\n}\r\n")
    assert target.read_bytes() == b"int main() {\n  return 0;\n}\n"
    assert [p.name for p in tmp_path.iterdir()] == ["AC_ref.cpp"]
