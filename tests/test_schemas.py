"""Every case is valid under the schema of a case, and every reference in its schemas resolves.

The schema of a case says that its two schemas are valid draft 2020-12. A reference resolves
inside its schema or to a metaschema of the draft: no schema needs another document. Upstream
cases that are not valid are left out of the corpus; ``overrides.json`` lists them.

The validator is ``jsonschema-rs``: over the million and a half schemas of the corpus it takes
seconds where ``jsonschema`` takes minutes.
"""

import json
from typing import TYPE_CHECKING

import jsonschema_rs
import pytest
from jsonschema_specifications import REGISTRY as METASCHEMAS
from referencing import Resource
from referencing.jsonschema import DRAFT202012

from reading import ROOT, cases, nested, read

if TYPE_CHECKING:
    from referencing._core import Resolver

    from subsumes_benchmark import Json

SCHEMA = ROOT / "schemas" / "case.schema.json"
# The metaschema comes with the validator; offline, it fetches nothing.
CASE_SCHEMA = jsonschema_rs.Draft202012Validator(
    json.loads(SCHEMA.read_text(encoding="utf-8")), offline=True
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


def unresolved_in(schema: Json, uri: str) -> list[str]:
    """The references of a schema that resolve neither inside it nor to a metaschema."""
    if not isinstance(schema, dict):
        return []
    identifier = schema.get("$id")
    base = identifier if isinstance(identifier, str) else uri
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resolver = METASCHEMAS.with_resource(base, resource).resolver(base_uri=base)
    return unresolved(schema, resolver, set())


@pytest.mark.slow
@pytest.mark.parametrize("collection", COLLECTIONS)
def test_cases_are_valid_and_their_schemas_resolve(collection: str) -> None:
    found = {}
    for case in cases():
        if case.collection != collection:
            continue
        document = read(case.file)
        assert isinstance(document, dict)
        # The schema of a case says that ``a`` and ``b`` are valid under the metaschema.
        problems = [
            f"{'/'.join(map(str, error.instance_path))}: {error.message[:160]}"
            for error in CASE_SCHEMA.iter_errors(document)
        ]
        problems += [
            f"{side}: {problem}"
            for side in ("a", "b")
            for problem in unresolved_in(document[side], f"urn:subsumes-benchmark:{case.id}:{side}")
        ]
        if problems:
            found[case.id] = problems
    assert found == {}
