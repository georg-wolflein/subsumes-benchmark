r"""Validating an instance the way this corpus reads a schema.

The validator is ``jsonschema``'s for draft 2020-12 with the keywords replaced whose reading
is the corpus's own:

- Those that match a regular expression match as ECMA-262 does with the ``u`` flag, which is
  what the specification recommends, through ``regress``, an ECMA-262 engine. Python's
  ``re``, which ``jsonschema`` uses, is another dialect: its ``\d`` matches every decimal
  digit of Unicode and its ``$`` also matches before a trailing newline, for two.
- ``format`` is asserted, through ``jsonschema-rs``, whose formats are those that the official
  test suite expects. Python's format checkers are not: they disagree with the suite on leap
  seconds and e-mail addresses.

The tests need it, and so does deriving a label from a counterexample; the build does not.
What it imports is in the ``validation`` dependency group.
"""

from collections.abc import Iterator
from functools import cache
from typing import Protocol

import jsonschema_rs
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import extend
from jsonschema_specifications import REGISTRY as METASCHEMAS
from referencing._core import Resolver
from regress import Regex, RegressError

from subsumes_benchmark import Json
from subsumes_benchmark.generated.case import Schema

# The formats that draft 2020-12 defines. With ``format`` asserted, it does not say what any
# other format accepts.
FORMATS = frozenset(
    {
        "date",
        "date-time",
        "duration",
        "email",
        "hostname",
        "idn-email",
        "idn-hostname",
        "ipv4",
        "ipv6",
        "iri",
        "iri-reference",
        "json-pointer",
        "regex",
        "relative-json-pointer",
        "time",
        "uri",
        "uri-reference",
        "uri-template",
        "uuid",
    }
)


class InvalidPatternError(Exception):
    """The pattern is not valid in ECMA-262 with the ``u`` flag."""


class UnknownFormatError(Exception):
    """The format is none that draft 2020-12 defines."""


@cache
def _compile(pattern: str) -> Regex | str:
    try:
        return Regex(pattern, flags="u")
    except RegressError as exc:
        return str(exc)


def pattern_error(pattern: str) -> str | None:
    """Why the pattern is not valid, or ``None`` if it is."""
    compiled = _compile(pattern)
    return compiled if isinstance(compiled, str) else None


def search(pattern: str, value: str) -> bool:
    """Whether the pattern matches somewhere in the string."""
    compiled = _compile(pattern)
    if isinstance(compiled, str):
        raise InvalidPatternError(pattern)
    value.encode()  # a lone surrogate is no string of a JSON document; fail rather than say no
    return compiled.find(value) is not None


@cache
def _format_checker(name: str) -> jsonschema_rs.Draft202012Validator:
    return jsonschema_rs.Draft202012Validator(
        {"format": name}, validate_formats=True, ignore_unknown_formats=False
    )


def conforms(name: str, value: str) -> bool:
    """Whether the string is one of the format.

    Raises:
        UnknownFormatError: Draft 2020-12 does not define the format.
    """
    if name not in FORMATS:
        raise UnknownFormatError(name)
    if name == "regex":
        return pattern_error(value) is None
    return _format_checker(name).is_valid(value)


def meaningless(schema: Json) -> str | None:
    """Why the corpus cannot say what the schema accepts, or ``None`` if it can.

    That is a pattern that is not valid, or a format that draft 2020-12 does not define.
    Every JSON object in the schema is looked at as if it were a schema, so data that reads
    like one is found too: the answer errs towards saying that the schema has no meaning.
    """
    pending = [schema]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        if not isinstance(node, dict):
            continue
        pending.extend(node.values())
        pattern, properties, name = (
            node.get("pattern"),
            node.get("patternProperties"),
            node.get("format"),
        )
        sources = [pattern] if isinstance(pattern, str) else []
        sources += list(properties) if isinstance(properties, dict) else []
        for source in sources:
            if pattern_error(source) is not None:
                return f"the pattern {source} is not valid"
        if isinstance(name, str) and name not in FORMATS:
            return f"the format {name} is not one of draft 2020-12"
    return None


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


def _format(
    validator: _Validating, name: Json, instance: Json, schema: Json
) -> Iterator[ValidationError]:
    if isinstance(instance, str) and isinstance(name, str) and not conforms(name, instance):
        yield ValidationError(f"{instance!r} is no {name}")


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
        "format": _format,
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


def is_valid_to_another(instance: Json, schema: Schema) -> bool:
    """What ``jsonschema-rs`` says, a validator that shares no code with the one above.

    It asserts ``format`` as well and reads a pattern in a dialect of its own, so the two may
    differ on a schema with patterns. Where both say the same, neither's mistake decides.
    """
    return jsonschema_rs.Draft202012Validator(
        schema, validate_formats=True, ignore_unknown_formats=False, offline=True
    ).is_valid(instance)
