"""Reading the committed corpus, for the tests."""

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

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


def nested(node: dict[str, Json]) -> Iterator[Json]:
    """The values of a schema object that can hold schemas, and so references.

    The value of a data keyword is left out. Under a keyword that maps names to schemas the
    schemas themselves are given: a property called ``default`` is a schema, not data.
    """
    for key, value in node.items():
        if key in NOT_SCHEMAS:
            continue
        if key in SCHEMA_MAPS | {"definitions"} and isinstance(value, dict):
            yield from value.values()
        else:
            yield value


def read(path: Path) -> Json:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    a_subsumes_b: bool | None
    b_subsumes_a: bool | None
    # The link to the upstream file of a case read from a source; a generated case has none.
    upstream: str | None
    generated: Json
    note: str | None
    duplicates: Sequence[str]
    derived: Json
    features: Sequence[str]

    @property
    def a(self) -> Json:
        """The schema that should accept everything; read from disk on every access."""
        return _document(self.file)["a"]

    @property
    def b(self) -> Json:
        """The schema whose instances must be accepted; read from disk on every access."""
        return _document(self.file)["b"]

    @property
    def collection(self) -> str:
        """The folder of the collection below the corpus: its origin and its name."""
        return self.id.rpartition("/")[0]

    @property
    def name(self) -> str:
        return self.id.rpartition("/")[2]

    @property
    def claims_nothing(self) -> bool:
        return self.a_subsumes_b is None and self.b_subsumes_a is None


def _label(value: Json) -> bool | None:
    assert value is None or isinstance(value, bool)
    return value


def _document(path: Path) -> dict[str, Json]:
    document = read(path)
    assert isinstance(document, dict)
    return document


def _case_id(path: Path) -> str:
    return path.relative_to(CORPUS).as_posix().removesuffix(".json")


@cache
def cases() -> Sequence[Case]:
    """Every case of the corpus: the JSON files in the folder of a collection of an origin.

    They are sorted by the folders and the name of the case.
    """
    found = []
    for path in sorted(CORPUS.glob("*/*/*.json"), key=lambda path: _case_id(path).split("/")):
        metadata = _document(path)
        upstream, note = metadata.get("upstream"), metadata.get("note")
        used = metadata["features"]
        assert isinstance(upstream, str) == (metadata["kind"] == "upstream")
        assert note is None or isinstance(note, str)
        assert isinstance(used, list)
        also = metadata.get("duplicates", [])
        assert isinstance(also, list)
        found.append(
            Case(
                id=_case_id(path),
                file=path,
                a_subsumes_b=_label(metadata["a_subsumes_b"]),
                b_subsumes_a=_label(metadata["b_subsumes_a"]),
                upstream=upstream if isinstance(upstream, str) else None,
                generated=metadata.get("generated"),
                note=note,
                duplicates=[str(link) for link in also],
                derived=metadata.get("derived"),
                features=[str(feature) for feature in used],
            )
        )
    return found


def case(case_id: str) -> Case:
    return _cases_by_id()[case_id]


@cache
def _cases_by_id() -> dict[str, Case]:
    return {case.id: case for case in cases()}


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
