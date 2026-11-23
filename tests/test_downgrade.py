"""The rewriting of a schema for a checker that reads an older draft."""

import pytest
from jsonschema import Draft4Validator, Draft7Validator, Draft202012Validator
from jsonschema.protocols import Validator

from reading import cases, constants
from subsumes_benchmark import Json
from subsumes_benchmark.compare.downgrade import OlderDraft, UnsupportedError, downgrade


def test_references_become_pointers_from_the_root() -> None:
    schema: Json = {
        "$id": "https://example.com/root",
        "$ref": "child#name",
        "$defs": {
            "https://example.com/child": {
                "$id": "child",
                "$defs": {"leaf": {"$anchor": "name", "type": "integer"}},
            }
        },
    }
    assert downgrade(schema, "draft-07") == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": {
            "https___example.com_child": {"definitions": {"leaf": {"type": "integer"}}}
        },
        "allOf": [{"$ref": "#/definitions/https___example.com_child/definitions/leaf"}],
    }


def test_a_pointer_follows_the_keyword_that_was_renamed() -> None:
    schema: Json = {
        "prefixItems": [{"type": "string"}],
        "items": {"$ref": "#/prefixItems/0"},
        "dependentSchemas": {"a": {"$ref": "#/items"}},
    }
    assert downgrade(schema, "draft-07") == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "items": [{"type": "string"}],
        "additionalItems": {"$ref": "#/items/0"},
        "dependencies": {"a": {"$ref": "#/additionalItems"}},
    }


def test_keywords_next_to_a_reference_still_apply() -> None:
    schema: Json = {"$ref": "#/$defs/a", "minimum": 1, "allOf": [True], "$defs": {"a": {}}}
    assert downgrade(schema, "draft-07") == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "minimum": 1,
        "allOf": [True, {"$ref": "#/definitions/a"}],
        "definitions": {"a": {}},
    }


def test_both_kinds_of_dependency_on_one_property() -> None:
    schema: Json = {
        "dependentRequired": {"a": ["b"], "c": []},
        "dependentSchemas": {"a": {"minProperties": 3}},
    }
    assert downgrade(schema, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "dependencies": {"a": {"allOf": [{"minProperties": 3}, {"required": ["b"]}]}},
    }


def test_draft_04_has_no_boolean_schema_and_no_const() -> None:
    schema: Json = {
        "properties": {"a": True, "b": False},
        "additionalProperties": False,
        "const": 1,
        "enum": [1, 2],
    }
    assert downgrade(schema, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "properties": {"a": {}, "b": {"not": {}}},
        "additionalProperties": False,
        "enum": [1, 2],
        "allOf": [{"enum": [1]}],
    }
    assert downgrade(False, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "not": {},
    }


def test_a_count_is_written_as_an_integer() -> None:
    schema: Json = {"maxItems": 2.0, "minLength": 1.0, "maximum": 2.0}
    assert downgrade(schema, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "maxItems": 2,
        "minLength": 1,
        "maximum": 2.0,
    }
    assert repr(downgrade(schema, "draft-07")).count("2.0") == 1


def test_an_enum_of_draft_04_lists_each_value_once_and_at_least_one() -> None:
    schema: Json = {"enum": [1, 1.0, True, "1", [1], [1.0], {"a": 1, "b": 2}, {"b": 2, "a": 1}]}
    assert downgrade(schema, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "enum": [1.0, True, "1", [1.0], {"b": 2, "a": 1}],
    }
    assert downgrade({"enum": []}, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "allOf": [{"not": {}}],
    }
    assert downgrade({"enum": [1, 1]}, "draft-07") == {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "enum": [1, 1],
    }


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"exclusiveMinimum": 1}, {"minimum": 1, "exclusiveMinimum": True}),
        ({"exclusiveMinimum": 1, "minimum": 1}, {"minimum": 1, "exclusiveMinimum": True}),
        ({"exclusiveMinimum": 1, "minimum": 2}, {"minimum": 2}),
        ({"exclusiveMinimum": 2, "minimum": 1}, {"minimum": 2, "exclusiveMinimum": True}),
        ({"exclusiveMaximum": 1, "maximum": 0}, {"maximum": 0}),
        ({"exclusiveMaximum": 0, "maximum": 1}, {"maximum": 0, "exclusiveMaximum": True}),
    ],
)
def test_an_exclusive_bound_is_a_flag_in_draft_04(schema: Json, expected: dict[str, Json]) -> None:
    assert downgrade(schema, "draft-04") == {
        "$schema": "http://json-schema.org/draft-04/schema#",
        **expected,
    }


def test_what_means_nothing_in_draft_2020_12_is_dropped() -> None:
    # ``additionalItems`` and ``dependencies`` would mean something in draft-07.
    schema: Json = {
        "additionalItems": False,
        "dependencies": {"a": ["b"]},
        "then": False,
        "minContains": 2,
        "title": "t",
        "unevaluatedProperties": True,
    }
    assert downgrade(schema, "draft-07") == {"$schema": "http://json-schema.org/draft-07/schema#"}


@pytest.mark.parametrize(
    ("schema", "target"),
    [
        ({"unevaluatedProperties": False}, "draft-07"),
        ({"unevaluatedItems": {"type": "string"}}, "draft-07"),
        ({"$dynamicRef": "#a"}, "draft-07"),
        ({"contains": {}, "minContains": 2}, "draft-07"),
        ({"contains": {}, "maxContains": 2}, "draft-07"),
        ({"$ref": "https://json-schema.org/draft/2020-12/schema"}, "draft-07"),
        ({"$ref": "#/examples/0", "examples": [{}]}, "draft-07"),
        ({"contains": {}}, "draft-04"),
        ({"if": {}}, "draft-04"),
        ({"propertyNames": {}}, "draft-04"),
    ],
)
def test_what_the_older_draft_cannot_express_is_refused(schema: Json, target: OlderDraft) -> None:
    with pytest.raises(UnsupportedError):
        downgrade(schema, target)


def integral(instance: Json) -> Json:
    """The instance with every number that has no fraction written as an integer.

    Whether ``1.0`` is an integer is the one thing the drafts disagree on that the rewriting
    leaves alone: a draft-04 validator may say no, and from draft-06 on it is one.
    """
    if isinstance(instance, float) and instance.is_integer():
        return int(instance)
    if isinstance(instance, list):
        return [integral(item) for item in instance]
    if isinstance(instance, dict):
        return {key: integral(value) for key, value in instance.items()}
    return instance


@pytest.mark.parametrize(
    ("target", "validator"), [("draft-07", Draft7Validator), ("draft-04", Draft4Validator)]
)
def test_a_rewritten_schema_accepts_the_same_instances(
    target: OlderDraft, validator: type[Validator]
) -> None:
    """Checked wherever ``b`` lists instances: each is valid under both or neither.

    Both validators match patterns with Python's ``re`` and leave ``format`` alone, so what
    they disagree on is the rewriting.
    """
    checked = 0
    for case in cases():
        instances = constants(case.b)
        if instances is None:
            continue
        instances = [integral(instance) for instance in instances]
        schema = case.a
        try:
            rewritten = downgrade(schema, target)
        except UnsupportedError:
            continue
        assert isinstance(schema, (dict, bool))
        assert isinstance(rewritten, dict)
        # Against the metaschema without its formats: ``regex`` would be Python's dialect.
        assert validator(validator.META_SCHEMA).is_valid(rewritten), case.id
        try:
            before = [Draft202012Validator(schema).is_valid(i) for i in instances]
            after = [validator(rewritten).is_valid(i) for i in instances]
        except Exception:
            continue  # a pattern that Python's ``re`` rejects, or a reference to a meta-schema
        assert before == after, case.id
        checked += 1
    assert checked > 2000
