"""Building inclusion cases from the official JSON Schema Test Suite.

A test case of the suite is a schema S with instances that are valid under it or not. That is
enough to build pairs of schemas whose inclusion is known without an inclusion checker:

- ``valid``: S against the ``const`` of an instance. S accepts it exactly when it is valid.
- ``nonvalid``: ``not S`` against the same ``const``. The answer is the opposite.
- ``unions``: S against an ``anyOf`` of the ``const`` of every valid instance, if there are
  several.
- ``reflexive``: S against itself.
- ``universal``: ``true`` against ``anyOf: [S, not S]``, which accepts everything.
- ``unsatisfiable``: ``false`` against ``allOf: [S, not S]``, which accepts nothing.

The categories are those of the containment test suite of Attouche et al. (ER 2021), which
built such pairs from the suite as it was in 2021.

Three of them need S inside another schema, once or twice. A copy of S means the same there
only if S neither names a location nor refers to one. Any other S goes under ``$defs`` once, as
a schema resource with an ``$id`` of its own, and is referenced by that ``$id``: the references
inside it then resolve as they did, and no identifier exists twice.
"""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self

from subsumes_benchmark.convert import ABSOLUTE_URI_RE, ConversionError, nested

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from subsumes_benchmark import Json

type Category = Literal["valid", "nonvalid", "unions", "reflexive", "universal", "unsatisfiable"]

# The number the suite's ``compatibility`` property gives draft 2020-12.
DRAFT_2020_12_RELEASE = 2020

# Keywords that name a location or refer to one. A schema that uses any of them means
# something only where it stands.
LOCATION_KEYWORDS = frozenset({"$id", "$anchor", "$dynamicAnchor", "$ref", "$dynamicRef"})

# The ``$id`` a schema gets to stand under ``$defs`` when it has none. The domain is reserved
# (RFC 2606), so it is no document that could be fetched.
SCHEMA_ID = "https://subsumes-benchmark.example/schema"


def compatible(constraints: str, release: int) -> bool:
    """Whether a test case with this ``compatibility`` applies to a release of the specification.

    This is the algorithm of the suite's README. The constraints are ordered from the oldest
    release to the newest: a bare number is a minimum, ``<=`` a maximum and ``=`` one release.
    """
    applies = True
    for constraint in constraints.split(","):
        if constraint.startswith("<="):
            version = int(constraint[2:])
            applies = release <= version
        elif constraint.startswith("="):
            version = int(constraint[1:])
            applies = release == version
        else:
            version = int(constraint)
            applies = release >= version
        if release <= version:
            break
    return applies


@dataclass(frozen=True)
class Instance:
    """One test of a test case: an instance and whether it is valid under the schema."""

    data: Json
    valid: bool


@dataclass(frozen=True)
class SuiteCase:
    """A test case of the suite: a schema, the schemas it may reference, and its tests."""

    schema: Json
    external_schemas: Mapping[str, Json]
    instances: Sequence[Instance]
    compatibility: str | None
    tags: Sequence[Json]

    @classmethod
    def create(cls, raw: Json) -> Self:
        assert isinstance(raw, dict)
        tests, external = raw["tests"], raw.get("externalSchemas", {})
        compatibility, tags = raw.get("compatibility"), raw.get("tags", [])
        assert isinstance(tests, list)
        assert isinstance(external, dict)
        assert compatibility is None or isinstance(compatibility, str)
        assert isinstance(tags, list)
        instances = []
        for test in tests:
            assert isinstance(test, dict)
            valid = test["valid"]
            assert isinstance(valid, bool)
            instances.append(Instance(test["data"], valid))
        return cls(raw["schema"], external, instances, compatibility, tags)

    @property
    def holds_for_the_corpus(self) -> bool:
        """Whether the expected results are those of draft 2020-12 with ``format`` asserted."""
        if "format-annotation" in self.tags:
            return False
        return self.compatibility is None or compatible(self.compatibility, DRAFT_2020_12_RELEASE)


@dataclass(frozen=True)
class Pair:
    """Two schemas whose inclusion is known, built from one test case.

    ``test`` is the index of the suite's test the pair was built from, for the categories that
    build one pair per test.
    """

    category: Category
    test: int | None
    a: Json
    b: Json
    a_subsumes_b: bool
    b_subsumes_a: bool | None = None


def self_contained(node: Json) -> bool:
    """Whether a schema neither names a location nor refers to one.

    A name under ``properties`` and the data under ``const`` are no keywords. The value of an
    unknown keyword is searched like a schema, which errs towards saying no.
    """
    if isinstance(node, list):
        return all(self_contained(item) for item in node)
    if not isinstance(node, dict):
        return True
    return not (node.keys() & LOCATION_KEYWORDS) and all(
        self_contained(value) for value in nested(node)
    )


def placed(schema: Json) -> tuple[Json, dict[str, Json]]:
    """What stands for the schema inside another schema, and the ``$defs`` that this needs."""
    if self_contained(schema):
        return schema, {}
    assert isinstance(schema, dict)
    identifier = schema.get("$id", SCHEMA_ID)
    if (
        not isinstance(identifier, str)
        or "#" in identifier
        or not ABSOLUTE_URI_RE.match(identifier)
    ):
        raise ConversionError(f"the schema's $id is no absolute URI: {identifier!r}")
    return {"$ref": identifier}, {"$defs": {identifier: {"$id": identifier} | schema}}


def negation(schema: Json) -> Json:
    """A schema that accepts exactly what the given one rejects."""
    inner, definitions = placed(schema)
    return {"not": inner} | definitions


def pairs(schema: Json, instances: Sequence[Instance]) -> Iterator[Pair]:
    """Every pair that one test case of the suite gives.

    The schema must stand on its own: the documents it references are embedded in it.
    """
    inner, definitions = placed(schema)
    negated = negation(schema)
    for index, instance in enumerate(instances):
        constant: Json = {"const": instance.data}
        yield Pair("valid", index, a=schema, b=constant, a_subsumes_b=instance.valid)
        yield Pair("nonvalid", index, a=negated, b=constant, a_subsumes_b=not instance.valid)
    # The suite gives some instances twice, and a union lists each once.
    accepted: dict[str, Json] = {
        json.dumps(instance.data, sort_keys=True): {"const": instance.data}
        for instance in instances
        if instance.valid
    }
    if len(accepted) > 1:
        yield Pair("unions", None, a=schema, b={"anyOf": [*accepted.values()]}, a_subsumes_b=True)
    yield Pair("reflexive", None, a=schema, b=schema, a_subsumes_b=True, b_subsumes_a=True)
    yield Pair(
        "universal",
        None,
        a=True,
        b={"anyOf": [inner, {"not": inner}]} | definitions,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    yield Pair(
        "unsatisfiable",
        None,
        a=False,
        b={"allOf": [inner, {"not": inner}]} | definitions,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
