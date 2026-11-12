"""Converting a schema written for an older draft to draft 2020-12."""

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urldefrag, urljoin

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from subsumes_benchmark import Json

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

# Keyword groups that decide how a schema is walked.
SCHEMA_MAP_KEYWORDS = frozenset(
    {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
)
SCHEMA_LIST_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
SCHEMA_KEYWORDS = frozenset(
    {
        "not",
        "items",
        "additionalItems",
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
VERBATIM_KEYWORDS = frozenset({"enum", "const", "default", "examples"})
# The inclusion artifact hoists the definitions of a fused pair under these names.
HOISTED_GROUPS = ("definitions1", "definitions2", "definitions3", "definitions4")
# Keywords whose value maps names to schemas. A key in such a map is a name, whatever it
# reads: a property called ``default`` is a schema, not a default value.
NAMED_SCHEMA_KEYWORDS = SCHEMA_MAP_KEYWORDS | {*HOISTED_GROUPS, "dependencies"}
ANCHOR_RE = re.compile(r"^[A-Za-z_][-A-Za-z0-9._]*$")
ABSOLUTE_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# A JSON pointer as its unescaped segments; a tuple because it keys the pointer map.
type Pointer = tuple[str, ...]
type PointerMap = dict[Pointer, Pointer]


class ConversionError(Exception):
    pass


def parse_pointer(fragment: str) -> Pointer:
    """``/a/b~1c`` -> ``("a", "b/c")``; the empty fragment is the root."""
    if fragment == "":
        return ()
    if not fragment.startswith("/"):
        raise ValueError(fragment)
    return tuple(
        seg.replace("~1", "/").replace("~0", "~") for seg in unquote(fragment).split("/")[1:]
    )


def format_pointer(pointer: Pointer) -> str:
    return "".join("/" + seg.replace("~", "~0").replace("/", "~1") for seg in pointer)


def map_pointer(pointer: Pointer, pmap: PointerMap) -> Pointer:
    """Map a pointer into the original document to the converted one, by longest prefix."""
    for length in range(len(pointer), -1, -1):
        prefix = pointer[:length]
        if prefix in pmap:
            return pmap[prefix] + pointer[length:]
    return pointer


def nested(node: dict[str, Json]) -> Iterator[Json]:
    """The values of a schema object that can hold schemas, and so references.

    The value of a data keyword such as ``const`` is left out. Under a keyword that maps names
    to schemas the schemas themselves are given, so that no name is taken for a keyword.
    """
    for key, value in node.items():
        if key in VERBATIM_KEYWORDS:
            continue
        if key in NAMED_SCHEMA_KEYWORDS and isinstance(value, dict):
            yield from value.values()
        else:
            yield value


def map_refs(node: Json, rewrite: Callable[[str], str]) -> Json:
    """A copy of a schema in which every ``$ref`` went through ``rewrite``."""
    if isinstance(node, list):
        return [map_refs(item, rewrite) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Json] = {}
    for key, value in node.items():
        if key == "$ref" and isinstance(value, str):
            out[key] = rewrite(value)
        elif key in NAMED_SCHEMA_KEYWORDS and isinstance(value, dict):
            out[key] = {name: map_refs(item, rewrite) for name, item in value.items()}
        elif key in VERBATIM_KEYWORDS:
            out[key] = value
        else:
            out[key] = map_refs(value, rewrite)
    return out


def dialect_of(schema: Json) -> str:
    """A short label for the ``$schema`` a source schema declared."""
    if not isinstance(schema, dict):
        return "boolean"
    value = schema.get("$schema")
    if not isinstance(value, str):
        return "undeclared"
    for key, label in (
        ("draft-03", "draft-03"),
        ("draft-04", "draft-04"),
        ("draft-06", "draft-06"),
        ("draft-07", "draft-07"),
        ("2019-09", "draft-2019-09"),
        ("2020-12", "draft-2020-12"),
    ):
        if key in value:
            return label
    if "iglucentral.com" in value:
        return "snowplow-self-describing"  # Snowplow's draft-04 based self-describing dialect
    if value.rstrip("#") in ("http://json-schema.org/schema", "https://json-schema.org/schema"):
        return "unversioned"  # json-schema.org/schema, "the latest draft"
    return "other"


class Converter:
    """Convert one document to draft 2020-12, recording where every node moved.

    Pass one (``convert``) rewrites keywords and absolutises references against the
    ``id``/``$id`` base in force; pass two (``rewrite_refs``) maps every pointer
    reference through the recorded moves, so a ``#/items/0`` that became
    ``#/prefixItems/0`` or a ``#/definitions/x`` that became ``#/$defs/x`` still points
    at the same node. Identifiers are dropped (except an absolute, fragment-less root
    ``$id``): both upstream tools resolve ``#/...`` against the document root, which is
    what a draft 2020-12 document without embedded resources does.

    ``notes`` names every kind of change that was applied.
    """

    def __init__(self) -> None:
        self.pmap: PointerMap = {}
        self.notes: set[str] = set()

    def convert(self, node: Json, *, old: Pointer = (), new: Pointer = (), base: str = "") -> Json:
        if isinstance(node, bool):
            self.pmap[old] = new
            return node
        if not isinstance(node, dict):
            raise ConversionError(f"schema is neither object nor boolean: {type(node).__name__}")
        self.pmap[old] = new
        root = old == ()
        out: dict[str, Json] = {}

        for key in ("id", "$id"):
            value = node.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                self.notes.add(f"{key} with non-string value dropped")
                continue
            url, fragment = urldefrag(value)
            if url:
                base = urljoin(base, url) if base else url
            if value.startswith("#") and len(value) > 1:
                if ANCHOR_RE.match(fragment):
                    out["$anchor"] = fragment
                    self.notes.add(f"{key} plain-name fragment -> $anchor")
                else:
                    self.notes.add(f"{key} fragment that is not a valid anchor dropped")
            elif root and not fragment and ABSOLUTE_URI_RE.match(url):
                out["$id"] = url
                if key == "id":
                    self.notes.add("root id -> $id")
            else:
                self.notes.add(f"{'nested ' if not root else 'root '}{key} dropped")

        if root:
            out["$schema"] = DRAFT_2020_12
        elif "$schema" in node:
            self.notes.add("nested $schema dropped")

        def sub(value: Json, old_key: str, new_key: str) -> Json:
            return self.convert(value, old=(*old, old_key), new=(*new, new_key), base=base)

        for key, value in node.items():
            if key in ("id", "$id", "$schema"):
                continue
            if key == "$ref":
                if not isinstance(value, str):
                    raise ConversionError("$ref is not a string")
                if not value.startswith("#") and base:
                    absolute = urljoin(base, value)
                    if absolute != value:
                        self.notes.add("ref absolutised against enclosing id")
                    value = absolute
                out["$ref"] = value
            elif key in ("exclusiveMinimum", "exclusiveMaximum") and isinstance(value, bool):
                bound = "minimum" if key == "exclusiveMinimum" else "maximum"
                self.notes.add(f"boolean {key} -> numeric")
                if value and bound in node:
                    out[key] = node[bound]
            elif key in ("minimum", "maximum") and node.get("exclusive" + key.capitalize()) is True:
                continue  # moved onto the exclusive keyword
            elif key == "items":
                if isinstance(value, list):
                    self.notes.add("items array -> prefixItems")
                    out["prefixItems"] = [
                        self.convert(
                            s,
                            old=(*old, "items", str(i)),
                            new=(*new, "prefixItems", str(i)),
                            base=base,
                        )
                        for i, s in enumerate(value)
                    ]
                    if "additionalItems" in node:
                        self.notes.add("additionalItems -> items")
                        out["items"] = sub(node["additionalItems"], "additionalItems", "items")
                else:
                    out["items"] = sub(value, "items", "items")
            elif key == "additionalItems":
                if not isinstance(node.get("items"), list):
                    self.notes.add(
                        "additionalItems without array items dropped (no effect in draft-04..07)"
                    )
            elif key == "dependencies":
                if not isinstance(value, dict):
                    raise ConversionError("dependencies is not an object")
                self.notes.add("dependencies -> dependentRequired/dependentSchemas")
                for name, dep in value.items():
                    if isinstance(dep, list):
                        required = out.setdefault("dependentRequired", {})
                        assert isinstance(required, dict)
                        required[name] = dep
                        self.pmap[(*old, "dependencies", name)] = (*new, "dependentRequired", name)
                    else:
                        schemas = out.setdefault("dependentSchemas", {})
                        assert isinstance(schemas, dict)
                        schemas[name] = self.convert(
                            dep,
                            old=(*old, "dependencies", name),
                            new=(*new, "dependentSchemas", name),
                            base=base,
                        )
            elif key == "$defs" or key == "definitions" or key in HOISTED_GROUPS:
                # Every definition namespace is flattened into one ``$defs``: a nested
                # namespace would read as a schema whose definition names are keywords. The
                # hoisted groups of one side may reuse a name, so a later duplicate is
                # prefixed with its group and the pointer map carries the rename.
                if not isinstance(value, dict):
                    raise ConversionError(f"{key} is not an object")
                defs = out.setdefault("$defs", {})
                assert isinstance(defs, dict)
                if key == "definitions":
                    self.notes.add("definitions -> $defs")
                elif key in HOISTED_GROUPS:
                    self.notes.add(
                        "hoisted definitions restored under $defs"
                        if root
                        else "nested hoisted-group keyword -> $defs"
                    )
                self.pmap[(*old, key)] = (*new, "$defs")
                for name, item in value.items():
                    unique = name
                    if unique in defs:
                        unique = f"{key}__{name}"
                        self.notes.add("definition renamed to avoid a collision between namespaces")
                    if unique in defs:
                        raise ConversionError(f"$defs collision on {unique!r}")
                    defs[unique] = self.convert(
                        item, old=(*old, key, name), new=(*new, "$defs", unique), base=base
                    )
            elif key in SCHEMA_MAP_KEYWORDS:
                if not isinstance(value, dict):
                    raise ConversionError(f"{key} is not an object")
                out[key] = {
                    name: self.convert(
                        item, old=(*old, key, name), new=(*new, key, name), base=base
                    )
                    for name, item in value.items()
                }
            elif key in SCHEMA_LIST_KEYWORDS:
                if not isinstance(value, list):
                    raise ConversionError(f"{key} is not an array")
                out[key] = [
                    self.convert(item, old=(*old, key, str(i)), new=(*new, key, str(i)), base=base)
                    for i, item in enumerate(value)
                ]
            elif key in SCHEMA_KEYWORDS:
                out[key] = sub(value, key, key)
            elif key in VERBATIM_KEYWORDS:
                out[key] = value
            elif key in ("$recursiveRef", "$recursiveAnchor"):
                raise ConversionError(f"{key} is not converted")
            else:
                # Assertions and annotations spelled the same in every draft, and unknown
                # keywords, which draft 2020-12 permits and both upstream tools ignore.
                out[key] = value
        return out

    def rewrite_refs(self, node: Json, resource_maps: dict[str, PointerMap]) -> Json:
        """Pass two: rewrite every pointer reference, local or into a converted resource."""

        def rewrite(value: str) -> str:
            url, fragment = urldefrag(value)
            pmap = self.pmap if not url else resource_maps.get(url)
            if pmap is not None and (fragment == "" or fragment.startswith("/")):
                try:
                    pointer = parse_pointer(fragment)
                except ValueError:
                    pointer = None
                if pointer is not None:
                    mapped = map_pointer(pointer, pmap)
                    if mapped != pointer:
                        self.notes.add("pointer reference rewritten to the converted path")
                    fragment = format_pointer(mapped)
            if url or fragment != "" or value.startswith("#"):
                return url + "#" + fragment
            return value

        return map_refs(node, rewrite)
