"""The pairs the build constructs from a test case of the official test suite."""

import json
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from subsumes_benchmark.build import (
    Collection,
    CollectionSpec,
    Source,
    SourceSpec,
    as_doubles,
    read_test_suite,
)
from subsumes_benchmark.convert import ConversionError
from subsumes_benchmark.testsuite import (
    SCHEMA_ID,
    Instance,
    Pair,
    compatible,
    negation,
    pairs,
    self_contained,
)
from subsumes_benchmark.validation import is_valid

if TYPE_CHECKING:
    from pathlib import Path

    from subsumes_benchmark import Json


def test_compatibility_follows_the_algorithm_of_the_suite() -> None:
    applies = {
        "7": True,
        "2020": True,
        "=2020": True,
        "2019,<=2020": True,
        "=3,7,<=2020": True,
        "<=3,7": True,
        "<=2020": True,
        "<=2019": False,
        "6,<=2019": False,
        "=2019": False,
        "9999": False,
        "4,<=6,9999": False,
    }
    assert {spec: compatible(spec, 2020) for spec in applies} == applies
    assert compatible("=3,7,<=2020", 3)
    assert not compatible("=3,7,<=2020", 4)
    assert not compatible("<=3,7", 6)


def test_a_schema_without_locations_is_copied_where_it_is_needed() -> None:
    schema: Json = {"minimum": 1}
    assert list(pairs(schema, [Instance(2, True), Instance(0, False), Instance("x", True)])) == [
        Pair("valid", 0, a=schema, b={"const": 2}, a_subsumes_b=True),
        Pair("nonvalid", 0, a={"not": schema}, b={"const": 2}, a_subsumes_b=False),
        Pair("valid", 1, a=schema, b={"const": 0}, a_subsumes_b=False),
        Pair("nonvalid", 1, a={"not": schema}, b={"const": 0}, a_subsumes_b=True),
        Pair("valid", 2, a=schema, b={"const": "x"}, a_subsumes_b=True),
        Pair("nonvalid", 2, a={"not": schema}, b={"const": "x"}, a_subsumes_b=False),
        Pair(
            "unions",
            None,
            a=schema,
            b={"anyOf": [{"const": 2}, {"const": "x"}]},
            a_subsumes_b=True,
        ),
        Pair("reflexive", None, a=schema, b=schema, a_subsumes_b=True, b_subsumes_a=True),
        Pair(
            "universal",
            None,
            a=True,
            b={"anyOf": [schema, {"not": schema}]},
            a_subsumes_b=True,
            b_subsumes_a=True,
        ),
        Pair(
            "unsatisfiable",
            None,
            a=False,
            b={"allOf": [schema, {"not": schema}]},
            a_subsumes_b=True,
            b_subsumes_a=True,
        ),
    ]


def test_a_union_needs_two_different_valid_instances() -> None:
    def categories(instances: list[Instance]) -> list[str]:
        return [pair.category for pair in pairs(True, instances)]

    assert "unions" not in categories([Instance(1, True), Instance(2, False)])
    assert "unions" not in categories([Instance(1, True), Instance(1, True)])
    assert "unions" in categories([Instance(1, True), Instance(1.0, True)])


def test_a_schema_with_references_stands_under_defs_once() -> None:
    schema: Json = {"properties": {"foo": {"$ref": "#"}}, "additionalProperties": False}
    resource: Json = {"$id": SCHEMA_ID} | schema
    assert negation(schema) == {"not": {"$ref": SCHEMA_ID}, "$defs": {SCHEMA_ID: resource}}
    by_category = {pair.category: pair for pair in pairs(schema, [])}
    assert by_category["universal"].b == {
        "anyOf": [{"$ref": SCHEMA_ID}, {"not": {"$ref": SCHEMA_ID}}],
        "$defs": {SCHEMA_ID: resource},
    }
    assert by_category["unsatisfiable"].b == {
        "allOf": [{"$ref": SCHEMA_ID}, {"not": {"$ref": SCHEMA_ID}}],
        "$defs": {SCHEMA_ID: resource},
    }
    # Where the schema is not inside another one, it stays as it is.
    assert by_category["reflexive"].a is schema


def test_a_schema_keeps_the_id_it_has() -> None:
    schema: Json = {"$id": "https://example.com/tree", "items": {"$ref": "#"}}
    assert negation(schema) == {
        "not": {"$ref": "https://example.com/tree"},
        "$defs": {"https://example.com/tree": schema},
    }
    with pytest.raises(ConversionError):
        negation({"$id": "tree.json", "items": {"$ref": "#"}})
    with pytest.raises(ConversionError):
        negation({"$id": "https://example.com/tree#", "items": {"$ref": "#"}})


def test_names_and_data_are_no_keywords() -> None:
    assert self_contained({"properties": {"$ref": {"type": "string"}}, "const": {"$id": "x"}})
    assert self_contained(True)
    assert not self_contained({"properties": {"a": {"$anchor": "a"}}})
    assert not self_contained({"allOf": [{"$dynamicRef": "#node"}]})


def test_the_negation_of_a_recursive_schema_rejects_what_the_schema_accepts() -> None:
    # The reference to the root must keep meaning the schema, not its negation.
    schema: Json = {"properties": {"foo": {"$ref": "#"}}, "additionalProperties": False}
    accepted: list[Json] = [{}, {"foo": {"foo": {}}}, 1]
    rejected: list[Json] = [{"bar": 1}, {"foo": {"bar": 1}}]
    negated = negation(schema)
    by_category = {pair.category: pair for pair in pairs(schema, [])}
    for instance in accepted:
        assert is_valid(instance, schema)
        assert not is_valid(instance, negated)
    for instance in rejected:
        assert not is_valid(instance, schema)
        assert is_valid(instance, negated)
    for instance in accepted + rejected:
        assert is_valid(instance, by_category["universal"].b)
        assert not is_valid(instance, by_category["unsatisfiable"].b)


def test_numbers_are_read_as_doubles_and_the_lost_ones_are_named() -> None:
    text = '{"a": [1.10, 1e2, 12345678901234567890, 0.123456789123456789]}'
    lost: set[str] = set()
    assert as_doubles(json.loads(text, parse_float=Decimal), lost) == json.loads(text)
    assert lost == {"0.123456789123456789"}


SUITE: Json = {
    "description": "an example file",
    "tests": [
        {"description": "for 2020-12", "schema": {"type": "integer"}, "tests": []},
        {
            "description": "for older drafts",
            "compatibility": "<=2019",
            "schema": {"items": [{}]},
            "tests": [],
        },
        {
            "description": "format as an annotation",
            "tags": ["format-annotation"],
            "schema": {"format": "date"},
            "tests": [{"description": "any string", "data": "x", "valid": True}],
        },
        {
            "description": "an external schema",
            "compatibility": "2019",
            "schema": {"$ref": "http://localhost:1234/integer.json"},
            "externalSchemas": {"http://localhost:1234/integer.json": {"type": "integer"}},
            "tests": [{"description": "a string", "data": "x", "valid": False}],
        },
    ],
}


def suite(root: Path) -> Collection:
    source = Source(
        name="suite",
        spec=SourceSpec(forge="github", license="MIT", license_file="L"),
        root=root,
        repository="https://example.com/suite.git",
        commit="0" * 40,
    )
    spec = CollectionSpec(
        source="suite",
        path="tests",
        labels="by-construction",
        use_case="tool-checking",
        description="Examples.",
    )
    return Collection("suite", source, spec)


def test_the_test_cases_for_draft_2020_12_are_read(tmp_path: Path) -> None:
    (tmp_path / "tests" / "proposals").mkdir(parents=True)
    (tmp_path / "tests" / "optional").mkdir()
    (tmp_path / "tests" / "optional" / "example.json").write_text(json.dumps(SUITE))
    (tmp_path / "tests" / "proposals" / "example.json").write_text(json.dumps(SUITE))
    found = {found.id: found for found in read_test_suite(suite(tmp_path), {})}
    assert list(found) == [
        "suite/optional/example/0/reflexive",
        "suite/optional/example/0/universal",
        "suite/optional/example/0/unsatisfiable",
        "suite/optional/example/3/valid/0",
        "suite/optional/example/3/nonvalid/0",
        "suite/optional/example/3/reflexive",
        "suite/optional/example/3/universal",
        "suite/optional/example/3/unsatisfiable",
    ]
    file = f"https://example.com/suite/blob/{'0' * 40}/tests/optional/example.json"
    assert found["suite/optional/example/0/reflexive"].upstream == f"{file}#/tests/0"
    valid = found["suite/optional/example/3/valid/0"]
    assert valid.upstream == f"{file}#/tests/3/tests/0"
    assert (valid.b, valid.a_subsumes_b, valid.b_subsumes_a) == ({"const": "x"}, False, None)
    # The external schema is embedded under its URL, which is its $id.
    document: Json = {"$id": "http://localhost:1234/integer.json", "type": "integer"}
    assert valid.a == {
        "$ref": "http://localhost:1234/integer.json",
        "$defs": {"http://localhost:1234/integer.json": document},
    }


def test_a_number_that_a_double_does_not_hold_must_be_excluded(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "bignum.json").write_text(
        '{"description": "x", "tests": [{"description": "y", "schema": '
        '{"maximum": 0.123456789123456789}, "tests": []}]}'
    )
    with pytest.raises(ConversionError):
        list(read_test_suite(suite(tmp_path), {}))
    assert list(read_test_suite(suite(tmp_path), {"suite/bignum/0/*": "too precise"}))
    assert list(read_test_suite(suite(tmp_path), {"suite/bignum/*": "too precise"}))
