"""Reading the committed corpus, for the tests."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urldefrag, urljoin

from jsonschema_specifications import REGISTRY as METASCHEMAS
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

if TYPE_CHECKING:
    from collections.abc import Sequence

    from subsumes_benchmark import Json

ROOT = Path(__file__).parent.parent
CORPUS = ROOT / "corpus"

# Keywords whose value is a map of schemas, a list of schemas or one schema; everything else
# (``const``, ``enum``, ``default``, ``examples``, unknown keywords) holds no schema.
SCHEMA_MAPS = frozenset({"properties", "patternProperties", "$defs", "dependentSchemas"})
SCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
SCHEMAS = frozenset(
    {
        "not",
        "items",
        "additionalProperties",
        "contains",
        "propertyNames",
        "if",
        "then",
        "else",
        "unevaluatedProperties",
        "unevaluatedItems",
        "contentSchema",
    }
)
NOT_SCHEMAS = frozenset({"enum", "const", "default", "examples"})


def read(path: Path) -> Json:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Case:
    id: str
    folder: Path
    a_subsumes_b: bool | None
    b_subsumes_a: bool | None
    upstream: str
    note: str | None

    @property
    def a(self) -> Json:
        """The schema that should accept everything; read from disk on every access."""
        return read(self.folder / "a.json")

    @property
    def b(self) -> Json:
        """The schema whose instances must be accepted; read from disk on every access."""
        return read(self.folder / "b.json")

    @property
    def collection(self) -> str:
        return self.id.partition("/")[0]

    @property
    def claims_nothing(self) -> bool:
        return self.a_subsumes_b is None and self.b_subsumes_a is None


def _label(value: Json) -> bool | None:
    assert value is None or isinstance(value, bool)
    return value


@cache
def cases() -> Sequence[Case]:
    """Every case of the corpus: the folders that hold a ``case.json``."""
    found = []
    for path in sorted(CORPUS.rglob("case.json")):
        metadata = read(path)
        assert isinstance(metadata, dict)
        upstream, note = metadata["upstream"], metadata.get("note")
        assert isinstance(upstream, str)
        assert note is None or isinstance(note, str)
        found.append(
            Case(
                id=path.parent.relative_to(CORPUS).as_posix(),
                folder=path.parent,
                a_subsumes_b=_label(metadata["a_subsumes_b"]),
                b_subsumes_a=_label(metadata["b_subsumes_a"]),
                upstream=upstream,
                note=note,
            )
        )
    return found


def case(case_id: str) -> Case:
    return _cases_by_id()[case_id]


@cache
def _cases_by_id() -> dict[str, Case]:
    return {case.id: case for case in cases()}


@cache
def resources() -> dict[str, Json]:
    """The external documents the cases reference, by URL."""
    documents = read(CORPUS / "resources.json")
    assert isinstance(documents, dict)
    return documents


@cache
def registry() -> Registry:
    """The metaschemas and the external documents, for resolving references."""
    registry: Registry = METASCHEMAS
    for url, contents in resources().items():
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(url, resource)
    return registry.crawl()


def _external_refs(node: Json, base: str, found: set[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _external_refs(item, base, found)
    elif isinstance(node, dict):
        identifier = node.get("$id")
        if isinstance(identifier, str):
            base = urljoin(base, identifier) if base else identifier
        for keyword in ("$ref", "$dynamicRef"):
            ref = node.get(keyword)
            if isinstance(ref, str) and not ref.startswith("#"):
                found.add(urldefrag(urljoin(base, ref) if base else ref)[0])
        for key, value in node.items():
            if key not in NOT_SCHEMAS:
                _external_refs(value, base, found)


def referenced_documents(schema: Json) -> set[str]:
    """The URLs of the external documents a schema reaches through its references."""
    reached: set[str] = set()
    pending: set[str] = set()
    _external_refs(schema, "", pending)
    while pending:
        url = pending.pop()
        if url in reached or url not in resources():
            continue
        reached.add(url)
        _external_refs(resources()[url], url, pending)
    return reached


def subschemas(schema: Json) -> list[dict[str, Json]]:
    """The schema and every schema nested in it, as far as they are objects."""
    if not isinstance(schema, dict):
        return []
    found = [schema]
    for key, value in schema.items():
        if key in SCHEMA_MAPS and isinstance(value, dict):
            for sub in value.values():
                found += subschemas(sub)
        elif key in SCHEMA_LISTS and isinstance(value, list):
            for sub in value:
                found += subschemas(sub)
        elif key in SCHEMAS:
            found += subschemas(value)
    return found


def patterns(schema: Json) -> set[str]:
    """Every regular expression a schema uses, in ``pattern`` and ``patternProperties``."""
    found: set[str] = set()
    for sub in subschemas(schema):
        pattern = sub.get("pattern")
        if isinstance(pattern, str):
            found.add(pattern)
        pattern_properties = sub.get("patternProperties")
        if isinstance(pattern_properties, dict):
            found.update(pattern_properties)
    return found


def uses_format(schema: Json) -> bool:
    return any(isinstance(sub.get("format"), str) for sub in subschemas(schema))


def constants(schema: Json) -> list[Json] | None:
    """The instances of a schema that only lists them, else ``None``.

    Such a schema is a ``const``, an ``enum`` or an ``anyOf`` of those, as the test suite's
    generator writes them. A label with such a schema on the narrower side can be checked by
    validating each instance against the other schema.
    """
    if not isinstance(schema, dict):
        return None
    keys = schema.keys() - {"$schema"}
    if keys == {"const"}:
        return [schema["const"]]
    if keys == {"enum"} and isinstance(schema["enum"], list):
        return list(schema["enum"])
    if keys == {"anyOf"} and isinstance(schema["anyOf"], list):
        found: list[Json] = []
        for branch in schema["anyOf"]:
            instances = constants(branch)
            if instances is None:
                return None
            found += instances
        return found
    return None
