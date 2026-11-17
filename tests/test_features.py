"""The ``features`` of a case: what its two schemas use."""

from typing import TYPE_CHECKING

import pytest
from jsonschema_specifications import REGISTRY as METASCHEMAS
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from reading import cases
from subsumes_benchmark.features import (
    FEATURES,
    METASCHEMAS as METASCHEMA_URL,
    NOT_KEYWORDS,
    References,
    UnresolvedReferenceError,
    features,
)

if TYPE_CHECKING:
    from referencing._core import Resolver

    from subsumes_benchmark import Json


def test_the_keywords_are_those_that_decide_what_a_schema_accepts() -> None:
    # The vocabularies of draft 2020-12 that assert or apply, and the two kinds of reference.
    # ``format`` is in the vocabulary that annotates, and the corpus asserts it.
    vocabularies = ("applicator", "unevaluated", "validation", "format-annotation")
    expected = {"$ref", "$dynamicRef"}
    for vocabulary in vocabularies:
        metaschema = METASCHEMAS[f"{METASCHEMA_URL}meta/{vocabulary}"].contents
        expected |= metaschema["properties"].keys()
    assert set(FEATURES) - NOT_KEYWORDS == expected
    assert list(FEATURES) == sorted(FEATURES)


def test_a_keyword_counts_only_where_a_schema_stands() -> None:
    schema: Json = {
        "title": "an annotation",
        "properties": {"format": {"const": {"minimum": 1}}, "enum": True},
        "x-unknown": {"pattern": "a"},
        "contentSchema": {"maxLength": 1},
        "examples": [{"type": "string"}],
    }
    assert features(schema) == ["const", "properties"]


def test_a_definition_counts_only_when_a_reference_leads_to_it() -> None:
    schema: Json = {
        "$defs": {"used": {"type": "string"}, "unused": {"minLength": 1}},
        "items": {"$ref": "#/$defs/used"},
    }
    assert features(schema) == ["$ref", "items", "type"]


def test_a_reference_is_followed_through_identifiers_and_anchors() -> None:
    schema: Json = {
        "$id": "https://example.com/root",
        "anyOf": [{"$ref": "child#leaf"}, {"$ref": "child#/$defs/a~1b"}, {"$ref": "child"}],
        "$defs": {
            "https://example.com/child": {
                "$id": "child",
                "maxItems": 1,
                "$defs": {
                    "leaf": {"$anchor": "leaf", "$ref": "#/$defs/own"},
                    "a/b": {"multipleOf": 2},
                    "own": {"uniqueItems": True},
                },
            },
            "own": {"minItems": 1},
        },
    }
    assert features(schema) == ["$ref", "anyOf", "maxItems", "multipleOf", "uniqueItems"]


def test_a_reference_to_any_place_in_the_document_is_followed() -> None:
    schema: Json = {"$ref": "#/x-shapes/0/square", "x-shapes": [{"square": {"minProperties": 1}}]}
    assert features(schema) == ["$ref", "minProperties"]


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "#"},
        {"properties": {"next": {"$ref": "#"}}},
        {
            "$ref": "#/$defs/a",
            "$defs": {"a": {"not": {"$ref": "#/$defs/b"}}, "b": {"$ref": "#/$defs/a"}},
        },
    ],
)
def test_recursion_is_a_schema_reached_again_from_itself(schema: Json) -> None:
    assert "recursion" in features(schema)


def test_a_schema_reached_twice_is_not_recursion() -> None:
    schema: Json = {
        "$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"type": "null"}},
        "allOf": [{"$ref": "#/$defs/a"}, {"$ref": "#/$defs/a"}, {"$ref": "#/$defs/b"}],
    }
    assert features(schema) == ["$ref", "allOf", "type"]


def test_a_dynamic_reference_leads_to_every_dynamic_anchor_of_its_name() -> None:
    schema: Json = {
        "$id": "https://example.com/root",
        "$dynamicRef": "#node",
        "$defs": {
            "first": {"$dynamicAnchor": "node", "minimum": 1},
            "other": {"$id": "other", "$dynamicAnchor": "node", "maximum": 1},
            "unrelated": {"$dynamicAnchor": "leaf", "const": 1},
        },
    }
    assert features(schema) == ["$dynamicRef", "maximum", "minimum"]


def test_a_reference_to_a_metaschema_is_not_followed() -> None:
    schema: Json = {"$ref": "https://json-schema.org/draft/2020-12/schema"}
    assert features(schema) == ["$ref"]


def test_the_features_of_a_case_are_those_of_both_schemas() -> None:
    assert features({"type": "string"}, {"minLength": 1}, True) == ["minLength", "type"]
    assert features(True, False) == []


def test_a_reference_that_leads_nowhere_is_an_error() -> None:
    for reference in ("#/$defs/missing", "#missing", "https://example.com/elsewhere"):
        with pytest.raises(UnresolvedReferenceError):
            features({"$ref": reference})


def test_a_schema_may_nest_deeper_than_python_recurses() -> None:
    schema: dict[str, Json] = {"type": "null"}
    for _ in range(5000):
        schema = {"not": schema}
    assert features(schema) == ["not", "type"]


@pytest.mark.slow
def test_every_case_lists_the_features_of_its_schemas() -> None:
    stale = [case.id for case in cases() if case.features != features(case.a, case.b)]
    assert stale == []


def disagreements(node: Json, resolver: Resolver[Json], references: References) -> list[str]:
    """The references of a schema that ``referencing`` resolves to another place."""
    if not isinstance(node, dict):
        return []
    if isinstance(node.get("$id"), str):
        resolver = resolver.in_subresource(
            Resource.from_contents(node, default_specification=DRAFT202012)
        )
    found = []
    for keyword in ("$ref", "$dynamicRef"):
        reference = node.get(keyword)
        if not isinstance(reference, str):
            continue
        resolved = references.resolve(reference, references.bases[id(node)])
        if resolved is not None and resolved[0] is not resolver.lookup(reference).contents:
            found.append(f"{keyword} {reference}")
    for child in References.subschemas(node):
        found += disagreements(child, resolver, references)
    return found


@pytest.mark.slow
def test_references_lead_where_the_referencing_library_says() -> None:
    """The resolution that ``features`` rests on, against an implementation of the draft."""
    found = {}
    checked = 0
    for case in cases():
        for side, schema in (("a", case.a), ("b", case.b)):
            if not isinstance(schema, dict):
                continue
            identifier = schema.get("$id")
            base = identifier if isinstance(identifier, str) else f"urn:case:{side}"
            resource = Resource.from_contents(schema, default_specification=DRAFT202012)
            resolver = METASCHEMAS.with_resource(base, resource).resolver(base_uri=base)
            if wrong := disagreements(schema, resolver, References(schema)):
                found[f"{case.id}/{side}.json"] = wrong
            checked += 1
    assert found == {}
    assert checked > 25000
