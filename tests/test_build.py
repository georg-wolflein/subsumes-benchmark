"""The two transformations of the build: splitting a fused test and converting to 2020-12."""

from typing import TYPE_CHECKING

import pytest

from subsumes_benchmark.build import case_name
from subsumes_benchmark.convert import DRAFT_2020_12, ConversionError, Converter
from subsumes_benchmark.unfuse import unfuse

if TYPE_CHECKING:
    from subsumes_benchmark import Json


def convert(schema: Json) -> Json:
    converter = Converter()
    return converter.rewrite_refs(converter.convert(schema), {})


def test_array_items_become_prefix_items_and_references_follow() -> None:
    assert convert(
        {
            "items": [{"type": "string"}, {"$ref": "#/items/0"}],
            "additionalItems": {"$ref": "#/definitions/tail"},
            "definitions": {"tail": {"type": "integer"}},
        }
    ) == {
        "$schema": DRAFT_2020_12,
        "prefixItems": [{"type": "string"}, {"$ref": "#/prefixItems/0"}],
        "items": {"$ref": "#/$defs/tail"},
        "$defs": {"tail": {"type": "integer"}},
    }


def test_dependencies_split_by_kind() -> None:
    assert convert({"dependencies": {"a": ["b"], "c": {"required": ["d"]}}}) == {
        "$schema": DRAFT_2020_12,
        "dependentRequired": {"a": ["b"]},
        "dependentSchemas": {"c": {"required": ["d"]}},
    }


def test_boolean_exclusive_bounds_become_numeric() -> None:
    assert convert(
        {"minimum": 1, "exclusiveMinimum": True, "maximum": 5, "exclusiveMaximum": False}
    ) == {
        "$schema": DRAFT_2020_12,
        "exclusiveMinimum": 1,
        "maximum": 5,
    }


def test_identifiers_are_dropped_except_an_absolute_root_id() -> None:
    assert convert(
        {
            "id": "http://example.com/root.json",
            "properties": {"a": {"id": "#named"}, "b": {"id": "nested.json", "$ref": "other.json"}},
        }
    ) == {
        "$schema": DRAFT_2020_12,
        "$id": "http://example.com/root.json",
        "properties": {
            "a": {"$anchor": "named"},
            # A reference to another document is absolutised and gets an empty fragment.
            "b": {"$ref": "http://example.com/other.json#"},
        },
    }


def test_keywords_of_draft_2019_09_recursion_are_refused() -> None:
    with pytest.raises(ConversionError):
        convert({"$recursiveRef": "#"})


def test_unfuse_restores_both_sides_with_the_definitions_they_use() -> None:
    first: Json = {"$ref": "#/definitions1/x"}
    second: Json = {"$ref": "#/definitions3/y"}
    fused: Json = {
        "allOf": [
            {"properties": {"p": {"$ref": "#/allOf/0/properties/q"}, "q": first}},
            {"not": {"items": second, "not": {"$ref": "#/allOf/1/not"}}},
        ],
        "definitions1": {"x": {"type": "object"}},
        "definitions3": {"y": {"type": "integer"}},
        "anyOf": [first, {"not": first}, second, {"not": second}],
    }
    assert unfuse(fused) == (
        {
            "properties": {"p": {"$ref": "#/properties/q"}, "q": {"$ref": "#/definitions1/x"}},
            "definitions1": {"x": {"type": "object"}},
        },
        {
            "items": {"$ref": "#/definitions3/y"},
            "not": {"$ref": "#"},
            "definitions3": {"y": {"type": "integer"}},
        },
        {"top-level tautology anyOf dropped"},
    )


def test_unfuse_refuses_what_the_artifact_does_not_emit() -> None:
    with pytest.raises(ConversionError):
        unfuse({"allOf": [{}, {}]})
    with pytest.raises(ConversionError):
        unfuse({"allOf": [{}, {"not": {}}], "title": "extra"})


def test_synthesized_file_names_become_paths() -> None:
    name = "draft2019_09_nonvalid_additionalItems_id10_subschema1_not_2"
    assert case_name(name) == "draft2019-09/nonvalid/additionalItems/10"
    assert (
        case_name("draft4_valid_boolean_schema_id3_subschema1_not_2")
        == "draft4/valid/boolean_schema/3"
    )
    assert case_name("agripparc-1.2_v2_not_v1") == "agripparc-1.2_v2_not_v1"
