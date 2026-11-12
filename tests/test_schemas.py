"""Every schema of the corpus is valid draft 2020-12 and every reference in it resolves.

Upstream cases that are not are left out of the corpus; ``overrides.toml`` lists them.
"""

from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from reading import cases, nested, registry, resources

if TYPE_CHECKING:
    from referencing._core import Resolver

    from subsumes_benchmark import Json

METASCHEMA = Draft202012Validator(Draft202012Validator.META_SCHEMA)
# Keywords whose values the metaschema types but no validator acts on. SchemaStore writes
# ``"deprecated": "use X instead"``, which changes nothing about what a schema accepts.
ANNOTATIONS = frozenset(
    {
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        "$comment",
    }
)
COLLECTIONS = sorted({case.collection for case in cases()})


def unresolved(node: Json, resolver: Resolver[Json], seen: set[int]) -> list[str]:
    """The references that do not resolve in the scope their enclosing ``$id`` establishes."""
    if isinstance(node, list):
        return [problem for item in node for problem in unresolved(item, resolver, seen)]
    if not isinstance(node, dict) or id(node) in seen:
        return []
    seen.add(id(node))
    if isinstance(node.get("$id"), str):
        resolver = resolver.in_subresource(
            Resource.from_contents(node, default_specification=DRAFT202012)
        )
    problems = []
    for keyword in ("$ref", "$dynamicRef"):
        ref = node.get(keyword)
        if isinstance(ref, str):
            try:
                resolver.lookup(ref)
            except Exception as exc:
                problems.append(f"unresolved {keyword} {ref}: {type(exc).__name__}")
    for value in nested(node):
        problems += unresolved(value, resolver, seen)
    return problems


def problems_of(schema: Json, uri: str) -> list[str]:
    problems = [
        f"metaschema: {error.message[:160]}"
        for error in METASCHEMA.iter_errors(schema)
        if not (error.absolute_path and str(error.absolute_path[-1]) in ANNOTATIONS)
    ]
    if not isinstance(schema, dict):
        return problems
    identifier = schema.get("$id")
    base = identifier if isinstance(identifier, str) else uri
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resolver = registry().with_resource(base, resource).resolver(base_uri=base)
    return problems + unresolved(schema, resolver, set())


@pytest.mark.slow
@pytest.mark.parametrize("collection", COLLECTIONS)
def test_schemas_are_valid_and_resolve(collection: str) -> None:
    found = {}
    for case in cases():
        if case.collection != collection:
            continue
        problems = [
            f"{side}.json: {problem}"
            for side, schema in (("a", case.a), ("b", case.b))
            for problem in problems_of(schema, f"urn:subsumes-benchmark:{case.id}:{side}")
        ]
        if problems:
            found[case.id] = problems
    assert found == {}


@pytest.mark.slow
def test_external_documents_are_valid_and_resolve() -> None:
    found = {url: problems_of(document, url) for url, document in resources().items()}
    assert {url: problems for url, problems in found.items() if problems} == {}
