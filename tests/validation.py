r"""Validating an instance the way this corpus reads a schema.

The validator is ``jsonschema``'s for draft 2020-12 with the keywords that match a regular
expression replaced: they match in the dialect of the Rust ``regex`` crate, through
``pydantic-core``, which embeds that crate and is what Pydantic validates ``pattern`` with.
Python's ``re``, which ``jsonschema`` uses, is another dialect: its ``$`` also matches before
a trailing newline, for one.

``format`` is not asserted: Python's format checkers disagree with the official test suite on
leap seconds and e-mail addresses, so the tests that validate skip the schemas that use it.
"""

from functools import cache
from typing import TYPE_CHECKING, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from jsonschema.validators import extend
from jsonschema_specifications import REGISTRY as METASCHEMAS
from pydantic_core import SchemaError, SchemaValidator, core_schema

if TYPE_CHECKING:
    from collections.abc import Iterator

    from jsonschema.protocols import Validator
    from referencing._core import Resolver

    from subsumes_benchmark import Json


class InvalidPatternError(Exception):
    """The pattern is not valid in the Rust regex dialect."""


@cache
def _compile(pattern: str) -> SchemaValidator | str:
    try:
        return SchemaValidator(core_schema.str_schema(pattern=pattern, regex_engine="rust-regex"))
    except SchemaError as exc:
        return str(exc)


def pattern_error(pattern: str) -> str | None:
    """Why the Rust regex crate rejects the pattern, or ``None`` if it accepts it."""
    compiled = _compile(pattern)
    return compiled if isinstance(compiled, str) else None


def search(pattern: str, value: str) -> bool:
    """Whether the pattern matches somewhere in the string."""
    compiled = _compile(pattern)
    if isinstance(compiled, str):
        raise InvalidPatternError(pattern)
    value.encode()  # a lone surrogate is no string to the regex crate; fail rather than say no
    return compiled.isinstance_python(value)


class _Validating(Protocol):
    """The part of a ``jsonschema`` validator the replaced keywords use."""

    _resolver: Resolver[Json]

    def evolve(self, **changes: object) -> _Validating: ...
    def is_valid(self, instance: Json) -> bool: ...
    def iter_errors(self, instance: Json) -> Iterator[ValidationError]: ...


def _pattern(
    validator: _Validating, source: Json, instance: Json, schema: Json
) -> Iterator[ValidationError]:
    if isinstance(instance, str) and isinstance(source, str) and not search(source, instance):
        yield ValidationError(f"{instance!r} does not match {source!r}")


def _pattern_properties(
    validator: _Validating, patterns: Json, instance: Json, schema: Json
) -> Iterator[ValidationError]:
    if not isinstance(instance, dict) or not isinstance(patterns, dict):
        return
    for source, subschema in patterns.items():
        for name, value in instance.items():
            if search(source, name):
                yield from validator.evolve(schema=subschema).iter_errors(value)


def _additional(schema: dict[str, Json], instance: dict[str, Json]) -> list[str]:
    """The members ``properties`` and ``patternProperties`` do not cover."""
    properties = schema.get("properties")
    names = properties if isinstance(properties, dict) else {}
    patterns = schema.get("patternProperties")
    sources = list(patterns) if isinstance(patterns, dict) else []
    return [
        name
        for name in instance
        if name not in names and not any(search(source, name) for source in sources)
    ]


def _additional_properties(
    validator: _Validating, subschema: Json, instance: Json, schema: Json
) -> Iterator[ValidationError]:
    if not isinstance(instance, dict) or not isinstance(schema, dict):
        return
    for name in _additional(schema, instance):
        yield from validator.evolve(schema=subschema).iter_errors(instance[name])


def _evaluated(validator: _Validating, instance: dict[str, Json], schema: Json) -> set[str]:
    """The member names the schema evaluates on the instance, as draft 2020-12 defines it."""
    if not isinstance(schema, dict):
        return set()
    keys: set[str] = set()
    for keyword in ("$ref", "$dynamicRef"):
        ref = schema.get(keyword)
        if isinstance(ref, str):
            resolved = validator._resolver.lookup(ref)
            inner = validator.evolve(schema=resolved.contents, _resolver=resolved.resolver)
            keys |= _evaluated(inner, instance, resolved.contents)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        keys |= properties.keys() & instance.keys()
    patterns = schema.get("patternProperties")
    if isinstance(patterns, dict):
        keys |= {n for n in instance if any(search(s, n) for s in patterns)}
    for keyword in ("additionalProperties", "unevaluatedProperties"):
        if keyword in schema:
            sub = validator.evolve(schema=schema[keyword])
            keys |= {n for n, v in instance.items() if sub.is_valid(v)}
    dependent = schema.get("dependentSchemas")
    if isinstance(dependent, dict):
        for name, sub in dependent.items():
            if name in instance:
                keys |= _evaluated(validator, instance, sub)
    for keyword in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for sub in branches:
                if validator.evolve(schema=sub).is_valid(instance):
                    keys |= _evaluated(validator, instance, sub)
    if "if" in schema:
        if validator.evolve(schema=schema["if"]).is_valid(instance):
            keys |= _evaluated(validator, instance, schema["if"])
            if "then" in schema:
                keys |= _evaluated(validator, instance, schema["then"])
        elif "else" in schema:
            keys |= _evaluated(validator, instance, schema["else"])
    return keys


def _unevaluated_properties(
    validator: _Validating, subschema: Json, instance: Json, schema: Json
) -> Iterator[ValidationError]:
    if not isinstance(instance, dict):
        return
    evaluated = _evaluated(validator, instance, schema)
    sub = validator.evolve(schema=subschema)
    for name, value in instance.items():
        if name not in evaluated and not sub.is_valid(value):
            yield ValidationError(f"unevaluated property {name!r} is not valid")


_Validator = extend(
    Draft202012Validator,
    validators={
        "pattern": _pattern,
        "patternProperties": _pattern_properties,
        "additionalProperties": _additional_properties,
        "unevaluatedProperties": _unevaluated_properties,
    },
)


def validator(schema: Json) -> Validator:
    """A validator for the schema. Nothing is fetched: a schema of the corpus needs no document."""
    return _Validator(schema, registry=METASCHEMAS)


def is_valid(instance: Json, schema: Json) -> bool:
    return validator(schema).is_valid(instance)
