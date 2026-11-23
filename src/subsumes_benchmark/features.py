"""What the two schemas of a case use: the ``features`` of the case.

A feature is a keyword of draft 2020-12 that decides what a schema accepts, or
``recursion``, which is not a keyword: a schema is reached again from itself, through a
reference.

A keyword counts where validation can reach it: in the schema itself, in a subschema of a
schema that counts, and in the target of a reference in one. A definition that nothing
references does not count, nor does anything under a keyword that draft 2020-12 does not
know. A reference to a meta-schema of draft 2020-12 that is not part of the schema is not
followed. The list says what is written in the schemas, not what the answer depends on:
saying that would take an inclusion checker.
"""

from collections.abc import Iterator, Mapping, Sequence
from typing import get_args
from urllib.parse import unquote, urldefrag, urljoin

from subsumes_benchmark import Json
from subsumes_benchmark.convert import parse_pointer
from subsumes_benchmark.generated.case import Feature

# In the order a list of features is written in: that of the code points. The list itself is
# in ``schemas/case.schema.json``.
FEATURES: Sequence[Feature] = get_args(Feature.__value__)
NOT_KEYWORDS: frozenset[Feature] = frozenset({"recursion"})
_KEYWORDS: Mapping[str, Feature] = {name: name for name in FEATURES if name not in NOT_KEYWORDS}

# The keywords that apply subschemas, by the shape of their value.
_SCHEMA_MAPS = frozenset({"properties", "patternProperties", "dependentSchemas"})
_SCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMAS = frozenset(
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
    }
)
# Schemas that are not applied where they stand, and still hold identifiers and anchors.
_UNAPPLIED_SCHEMA_MAPS = frozenset({"$defs"})
_UNAPPLIED_SCHEMAS = frozenset({"contentSchema"})

METASCHEMAS = "https://json-schema.org/draft/2020-12/"

# A schema object with the base URI that references in it resolve against.
type _Located = tuple[dict[str, Json], str]


class UnresolvedReferenceError(Exception):
    pass


def _subschemas(node: dict[str, Json], *, unapplied: bool) -> Iterator[Json]:
    """The schemas directly inside a schema; those of ``$defs`` and such only on request."""
    for key, value in node.items():
        if key in _SCHEMA_MAPS or (unapplied and key in _UNAPPLIED_SCHEMA_MAPS):
            if isinstance(value, dict):
                yield from value.values()
        elif key in _SCHEMA_LISTS:
            if isinstance(value, list):
                yield from value
        elif key in _SCHEMAS or (unapplied and key in _UNAPPLIED_SCHEMAS):
            yield value


def _join(base: str, reference: str) -> str:
    """Resolve a reference against a base; ``urljoin`` ignores the base of a URN."""
    if reference == "" or reference.startswith("#"):
        return urldefrag(base).url + reference
    return urljoin(base, reference)


class References:
    """Where the references of one schema document lead.

    A schema object is told apart by its identity, so the document must not hold one object
    in two places; what ``json.loads`` returns does not.
    """

    def __init__(self, schema: Json) -> None:
        self.resources: dict[str, dict[str, Json]] = {}
        self.anchors: dict[tuple[str, str], _Located] = {}
        self.dynamic_anchors: dict[str, list[_Located]] = {}
        # The base in force inside every schema object that has a place in the document.
        self.bases: dict[int, str] = {}
        if isinstance(schema, dict):
            # A schema without ``$id`` has no URL; its references have none either.
            self.resources[""] = schema
        pending: list[tuple[Json, str]] = [(schema, "")]
        while pending:
            node, base = pending.pop()
            if not isinstance(node, dict):
                continue
            identifier = node.get("$id")
            if isinstance(identifier, str):
                base = urldefrag(_join(base, identifier)).url
                self.resources.setdefault(base, node)
            self.bases[id(node)] = base
            anchor, dynamic_anchor = node.get("$anchor"), node.get("$dynamicAnchor")
            if isinstance(anchor, str):
                self.anchors.setdefault((base, anchor), (node, base))
            if isinstance(dynamic_anchor, str):
                self.anchors.setdefault((base, dynamic_anchor), (node, base))
                self.dynamic_anchors.setdefault(dynamic_anchor, []).append((node, base))
            pending.extend((child, base) for child in _subschemas(node, unapplied=True))

    @staticmethod
    def subschemas(node: dict[str, Json]) -> Iterator[Json]:
        """The schemas directly inside a schema, applied where they stand or not."""
        return _subschemas(node, unapplied=True)

    def resolve(self, reference: str, base: str) -> tuple[Json, str] | None:
        """The schema a reference leads to and the base in force there.

        Args:
            reference: The value of a ``$ref`` or ``$dynamicRef``.
            base: The base in force where it is written.

        Returns:
            ``None`` for a reference to a meta-schema of draft 2020-12.

        Raises:
            UnresolvedReferenceError: The reference leads nowhere.
        """
        url, fragment = urldefrag(_join(base, reference))
        resource = self.resources.get(url)
        if resource is None:
            if url.startswith(METASCHEMAS):
                return None
            raise UnresolvedReferenceError(f"{reference}: {url or 'the schema'} is not in it")
        if fragment == "":
            return resource, url
        if not fragment.startswith("/"):
            located = self.anchors.get((url, unquote(fragment)))
            if located is None:
                raise UnresolvedReferenceError(f"{reference}: no such anchor")
            return located
        node: Json = resource
        for segment in parse_pointer(fragment):
            try:
                if isinstance(node, list):
                    node = node[int(segment)]
                elif isinstance(node, dict):
                    node = node[segment]
                else:
                    raise KeyError(segment)
            except (KeyError, IndexError, ValueError) as exc:
                raise UnresolvedReferenceError(f"{reference}: no such location") from exc
            url = self.bases.get(id(node), url)
        return node, url

    def targets(self, node: dict[str, Json], base: str) -> Sequence[_Located]:
        """The schema objects that the references of one schema object lead to.

        A ``$dynamicRef`` to a dynamic anchor may lead to every dynamic anchor of that name
        in the document, whichever the evaluation picks. A reference to a meta-schema of
        draft 2020-12 leads to nothing here.
        """
        found: list[_Located] = []
        for keyword in ("$ref", "$dynamicRef"):
            reference = node.get(keyword)
            if not isinstance(reference, str):
                continue
            resolved = self.resolve(reference, base)
            if resolved is not None and isinstance(resolved[0], dict):
                found.append((resolved[0], resolved[1]))
            if keyword == "$dynamicRef":
                found += self.dynamic_anchors.get(unquote(urldefrag(reference).fragment), [])
        return found


def _features_of(schema: Json) -> set[Feature]:
    if not isinstance(schema, dict):
        return set()
    references = References(schema)
    found: set[Feature] = set()

    def successors(node: dict[str, Json], base: str) -> Iterator[_Located]:
        found.update(_KEYWORDS[key] for key in node if key in _KEYWORDS)
        for child in _subschemas(node, unapplied=False):
            if isinstance(child, dict):
                yield child, references.bases.get(id(child), base)
        yield from references.targets(node, base)

    # A depth-first walk without recursion, since a schema may nest deeper than Python
    # recurses. ``finished`` is false for the schemas on the path from the root.
    root = references.bases[id(schema)]
    finished: dict[int, bool] = {id(schema): False}
    path: list[tuple[dict[str, Json], Iterator[_Located]]] = [(schema, successors(schema, root))]
    while path:
        node, rest = path[-1]
        for child, base in rest:
            state = finished.get(id(child))
            if state is None:
                finished[id(child)] = False
                path.append((child, successors(child, base)))
                break
            if not state:
                found.add("recursion")
        else:
            finished[id(node)] = True
            path.pop()
    return found


def features(*schemas: Json) -> Sequence[Feature]:
    """What the schemas use, in the order of ``FEATURES``.

    Raises:
        UnresolvedReferenceError: A reference in a schema leads nowhere.
    """
    found: set[Feature] = set()
    for schema in schemas:
        found |= _features_of(schema)
    return sorted(found)
