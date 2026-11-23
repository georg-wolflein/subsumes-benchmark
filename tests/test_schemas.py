"""Every reference in a schema of the corpus resolves.

A reference resolves inside its schema or to a metaschema of the draft: no schema needs
another document. That the schemas are valid draft 2020-12 is what the schema of a case says,
and ``test_structure.py`` holds every case against it. Upstream cases that fail either are
left out of the corpus; ``overrides.json`` lists them.
"""

import pytest
from jsonschema_specifications import REGISTRY as METASCHEMAS
from referencing import Resource
from referencing._core import Resolver
from referencing.jsonschema import DRAFT202012

from reading import cases, nested, read
from subsumes_benchmark import Json

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


def unresolved_in(schema: Json, uri: str) -> list[str]:
    """The references of a schema that resolve neither inside it nor to a metaschema."""
    if not isinstance(schema, dict):
        return []
    identifier = schema.get("$id")
    base = identifier if isinstance(identifier, str) else uri
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resolver = METASCHEMAS.with_resource(base, resource).resolver(base_uri=base)
    return unresolved(schema, resolver, set())


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_references_resolve(collection: str) -> None:
    found = {}
    for case in cases():
        if case.collection != collection:
            continue
        document = read(case.file)
        assert isinstance(document, dict)
        problems = [
            f"{side}: {problem}"
            for side in ("a", "b")
            for problem in unresolved_in(document[side], f"urn:subsumes-benchmark:{case.id}:{side}")
        ]
        if problems:
            found[case.id] = problems
    assert found == {}
