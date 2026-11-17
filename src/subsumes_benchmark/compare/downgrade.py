"""Rewriting a draft 2020-12 schema for a checker that reads an older draft.

The corpus is draft 2020-12, and some checkers read draft-04 or draft-07 only. Such a checker
gets every schema rewritten to its draft, so that what it answers is an answer about a schema
it understands. The rewriting keeps the set of valid instances; a schema that the older draft
cannot express is refused with ``UnsupportedError``, and the checker is not asked.

Three things change:

- **References.** Every ``$ref`` is resolved the way draft 2020-12 does, against ``$id`` and
  ``$anchor``, and replaced by a JSON pointer from the root of the document. The identifiers
  are then dropped, so the result is one resource whose references are all ``#/...``.
- **Keywords.** A keyword that the older draft spells differently is renamed. A keyword that
  the older draft does not have is refused; a logical encoding of it is not attempted.
- **Everything without a meaning.** Annotations and unknown keywords are dropped. Kept, an
  unknown keyword could turn into a keyword of the older draft: ``additionalItems`` means
  nothing in draft 2020-12 and something in draft-07.

One difference between the drafts is left alone: ``type: integer`` stays as it is, although
draft-04 lets an implementation take ``1.0`` for a number that is not an integer.
"""

import json
import re
from typing import TYPE_CHECKING, Literal, assert_never
from urllib.parse import quote, unquote, urldefrag, urljoin

from subsumes_benchmark.convert import Pointer, PointerMap, format_pointer, map_pointer

if TYPE_CHECKING:
    from subsumes_benchmark import Json

type OlderDraft = Literal["draft-04", "draft-07"]

META_SCHEMAS: dict[OlderDraft, str] = {
    "draft-04": "http://json-schema.org/draft-04/schema#",
    "draft-07": "http://json-schema.org/draft-07/schema#",
}

# Where a schema without ``$id`` is taken to live; any URL does, since only references
# inside the schema resolve.
ROOT_BASE = "https://subsumes-benchmark.invalid/schema"

DEFINITIONS = frozenset({"$defs", "definitions"})
SCHEMA_MAPS = frozenset({"properties", "patternProperties"})
SCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf"})
VERBATIM = frozenset(
    {
        "type",
        "enum",
        "multipleOf",
        "maximum",
        "minimum",
        "maxLength",
        "minLength",
        "pattern",
        "format",
        "maxItems",
        "minItems",
        "uniqueItems",
        "maxProperties",
        "minProperties",
    }
)
# What a schema location of draft 2020-12 can hold besides the keywords handled one by one;
# used to find every identifier and anchor before anything is rewritten.
INDEXED_MAPS = SCHEMA_MAPS | DEFINITIONS | {"dependentSchemas"}
INDEXED_LISTS = SCHEMA_LISTS | {"prefixItems"}
INDEXED_SCHEMAS = frozenset(
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
# Keywords whose value is a number of things.
COUNTS = frozenset(
    {"maxLength", "minLength", "maxItems", "minItems", "maxProperties", "minProperties"}
)
# Keywords that are rewritten together with the keywords they work with.
GROUPED = frozenset(
    {"dependentRequired", "dependentSchemas", "contains", "minContains", "maxContains"}
    | {"if", "then", "else"}
)
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class UnsupportedError(Exception):
    """The schema uses something the older draft cannot express."""


def _join(base: str, reference: str) -> str:
    """Resolve a reference against a base; ``urljoin`` ignores the base of a URN."""
    if reference == "" or reference.startswith("#"):
        return urldefrag(base).url + reference
    return urljoin(base, reference)


def _identity(value: Json) -> str:
    """A text that two JSON values share exactly when JSON Schema takes them for equal."""
    if isinstance(value, float) and value.is_integer():
        return json.dumps(int(value))
    if isinstance(value, list):
        return "[" + ",".join(_identity(item) for item in value) + "]"
    if isinstance(value, dict):
        members = (f"{json.dumps(key)}:{_identity(value[key])}" for key in sorted(value))
        return "{" + ",".join(members) + "}"
    return json.dumps(value)


def _parse_fragment_pointer(fragment: str) -> Pointer:
    return tuple(
        segment.replace("~1", "/").replace("~0", "~")
        for segment in unquote(fragment).split("/")[1:]
    )


class _Index:
    """Where every resource and anchor of a document is, as a pointer from its root."""

    def __init__(self, schema: Json) -> None:
        self.resources: dict[str, Pointer] = {}
        self.anchors: dict[tuple[str, str], Pointer] = {}
        # The base in force at every schema location, for resolving its ``$ref``.
        self.bases: dict[Pointer, str] = {}
        self._walk(schema, (), ROOT_BASE, root=True)

    def _walk(self, node: Json, at: Pointer, base: str, *, root: bool = False) -> None:
        if not isinstance(node, dict):
            self.bases[at] = base
            return
        identifier = node.get("$id")
        if isinstance(identifier, str):
            base = urldefrag(_join(base, identifier)).url
            self.resources.setdefault(base, at)
        elif root:
            self.resources[base] = at
        self.bases[at] = base
        for keyword in ("$anchor", "$dynamicAnchor"):
            name = node.get(keyword)
            if isinstance(name, str):
                self.anchors.setdefault((base, name), at)
        for key, value in node.items():
            if key in INDEXED_MAPS and isinstance(value, dict):
                for name, item in value.items():
                    self._walk(item, (*at, key, name), base)
            elif key in INDEXED_LISTS and isinstance(value, list):
                for i, item in enumerate(value):
                    self._walk(item, (*at, key, str(i)), base)
            elif key in INDEXED_SCHEMAS:
                self._walk(value, (*at, key), base)

    def resolve(self, reference: str, at: Pointer) -> Pointer:
        """The location a ``$ref`` written at ``at`` points to."""
        url, fragment = urldefrag(_join(self.bases[at], reference))
        if url not in self.resources:
            raise UnsupportedError(f"reference to {url}, which is not inside the schema")
        resource = self.resources[url]
        if fragment == "":
            return resource
        if fragment.startswith("/"):
            return (*resource, *_parse_fragment_pointer(fragment))
        anchor = self.anchors.get((url, unquote(fragment)))
        if anchor is None:
            raise UnsupportedError(f"reference to an anchor that does not exist: {reference}")
        return anchor


class _Downgrade:
    def __init__(self, schema: Json, target: OlderDraft) -> None:
        self.target = target
        self.index = _Index(schema)
        self.moved: PointerMap = {}
        # Every reference written out, with the location it must point to once all moved.
        self.references: list[tuple[dict[str, Json], Pointer]] = []

    def run(self, schema: Json) -> Json:
        out = self.schema(schema, (), ())
        if not isinstance(out, dict):
            out = {} if out else {"not": {}}
        for holder, target in self.references:
            if target not in self.moved:
                raise UnsupportedError(
                    f"reference to #{format_pointer(target)}, which is not a schema of the document"
                )
            pointer = format_pointer(map_pointer(target, self.moved))
            holder["$ref"] = "#" + quote(pointer, safe="/~!$&'()*+,;=:@")
        return {"$schema": META_SCHEMAS[self.target], **out}

    def schema(self, node: Json, old: Pointer, new: Pointer, *, boolean: bool = False) -> Json:
        """Rewrite the schema at ``old``, which will live at ``new``.

        ``boolean`` says that the place allows a boolean in every draft, as
        ``additionalProperties`` does; draft-04 allows it nowhere else.
        """
        self.moved[old] = new
        if isinstance(node, bool):
            if self.target == "draft-04" and not boolean:
                return {} if node else {"not": {}}
            return node
        if not isinstance(node, dict):
            raise UnsupportedError("a schema that is neither an object nor a boolean")

        out: dict[str, Json] = {}
        # Conjuncts that join ``allOf`` at the end, after the ones the schema wrote, so that
        # the pointers into those stay valid.
        extra: list[Json] = []
        reference: dict[str, Json] | None = None

        for key, value in node.items():
            if key == "$ref":
                if not isinstance(value, str):
                    raise UnsupportedError("$ref is not a string")
                reference = {"$ref": value}
                self.references.append((reference, self.index.resolve(value, old)))
            elif key == "$dynamicRef":
                raise UnsupportedError(f"$dynamicRef does not exist in {self.target}")
            elif key in DEFINITIONS and isinstance(value, dict):
                self.definitions(key, value, out, old, new)
            elif key in SCHEMA_MAPS and isinstance(value, dict):
                out[key] = {
                    name: self.schema(item, (*old, key, name), (*new, key, name))
                    for name, item in value.items()
                }
            elif key in SCHEMA_LISTS and isinstance(value, list):
                out[key] = [
                    self.schema(item, (*old, key, str(i)), (*new, key, str(i)))
                    for i, item in enumerate(value)
                ]
            elif key == "not":
                out[key] = self.schema(value, (*old, key), (*new, key))
            elif key == "additionalProperties":
                out[key] = self.schema(value, (*old, key), (*new, key), boolean=True)
            elif key == "prefixItems" and isinstance(value, list):
                out["items"] = [
                    self.schema(item, (*old, key, str(i)), (*new, "items", str(i)))
                    for i, item in enumerate(value)
                ]
            elif key == "items":
                if "prefixItems" in node:
                    out["additionalItems"] = self.schema(
                        value, (*old, key), (*new, "additionalItems"), boolean=True
                    )
                else:
                    out[key] = self.schema(value, (*old, key), (*new, key))
            elif key in GROUPED:
                pass  # together with the keywords it works with, below
            elif key in ("unevaluatedProperties", "unevaluatedItems"):
                if value is not True and value != {}:
                    raise UnsupportedError(f"{key} does not exist in {self.target}")
            elif key == "propertyNames":
                if self.target == "draft-04":
                    raise UnsupportedError("propertyNames does not exist in draft-04")
                out[key] = self.schema(value, (*old, key), (*new, key))
            elif key == "const":
                if self.target == "draft-04":
                    # ``enum`` is the same thing; next to an ``enum`` it is a second one.
                    if "enum" in node:
                        extra.append({"enum": [value]})
                    else:
                        out["enum"] = [value]
                else:
                    out[key] = value
            elif key == "required":
                # Draft-04 does not allow the empty list, which requires nothing anyway.
                if value != []:
                    out[key] = value
            elif key in ("exclusiveMinimum", "exclusiveMaximum"):
                if self.target != "draft-04":
                    out[key] = value
            elif key == "enum" and self.target == "draft-04" and isinstance(value, list):
                # Draft-04 wants at least one value and no value twice.
                distinct = list({_identity(item): item for item in value}.values())
                if distinct:
                    out[key] = distinct
                else:
                    extra.append({"not": {}})
            elif key in COUNTS and isinstance(value, float) and value.is_integer():
                out[key] = int(value)  # ``2.0`` is an integer only from draft-06 on
            elif key in VERBATIM:
                out[key] = value
            # Everything else is an annotation, an identifier or an unknown keyword.

        self.dependencies(node, out, old, new)
        self.contains(node, out, old, new)
        self.conditional(node, out, old, new)
        if self.target == "draft-04":
            self.exclusive_bounds(node, out)

        if reference is not None:
            if not out and not extra:
                return reference
            # Older drafts ignore what stands next to ``$ref``; draft 2020-12 applies both.
            extra.append(reference)
        if extra:
            written = out.get("allOf")
            out["allOf"] = [*(written if isinstance(written, list) else []), *extra]
        return out

    def definitions(
        self,
        key: str,
        value: dict[str, Json],
        out: dict[str, Json],
        old: Pointer,
        new: Pointer,
    ) -> None:
        """Move definitions under ``definitions``, under names that need no escaping.

        Some checkers follow a pointer without undoing its escapes, and a document embedded
        in the corpus is named by its URL.
        """
        self.moved[(*old, key)] = (*new, "definitions")
        definitions = out.setdefault("definitions", {})
        assert isinstance(definitions, dict)
        for name, item in value.items():
            safe = name if SAFE_NAME_RE.match(name) else re.sub(r"[^A-Za-z0-9_.-]", "_", name)
            unique, counter = safe, 1
            while unique in definitions:
                counter += 1
                unique = f"{safe}_{counter}"
            # Reserve the name before descending, in case of a collision further down.
            definitions[unique] = None
            definitions[unique] = self.schema(
                item, (*old, key, name), (*new, "definitions", unique)
            )

    def dependencies(
        self, node: dict[str, Json], out: dict[str, Json], old: Pointer, new: Pointer
    ) -> None:
        """``dependentRequired`` and ``dependentSchemas`` are one ``dependencies`` before 2019."""
        required = node.get("dependentRequired")
        schemas = node.get("dependentSchemas")
        dependencies: dict[str, Json] = {}
        if isinstance(schemas, dict):
            for name, item in schemas.items():
                names = required.get(name) if isinstance(required, dict) else None
                source = (*old, "dependentSchemas", name)
                target = (*new, "dependencies", name)
                if isinstance(names, list) and names:
                    dependencies[name] = {
                        "allOf": [
                            self.schema(item, source, (*target, "allOf", "0")),
                            {"required": names},
                        ]
                    }
                else:
                    dependencies[name] = self.schema(item, source, target)
        if isinstance(required, dict):
            for name, names in required.items():
                # Draft-04 does not allow the empty list, which requires nothing anyway.
                if name not in dependencies and names != []:
                    dependencies[name] = names
        if dependencies:
            out["dependencies"] = dependencies

    def contains(
        self, node: dict[str, Json], out: dict[str, Json], old: Pointer, new: Pointer
    ) -> None:
        if "contains" not in node:
            return  # minContains and maxContains mean nothing without it
        low = node.get("minContains", 1)
        if low == 0 and "maxContains" not in node:
            return  # any array contains at least no match
        if "maxContains" in node or low != 1:
            raise UnsupportedError(f"minContains and maxContains do not exist in {self.target}")
        if self.target == "draft-04":
            raise UnsupportedError("contains does not exist in draft-04")
        out["contains"] = self.schema(node["contains"], (*old, "contains"), (*new, "contains"))

    def conditional(
        self, node: dict[str, Json], out: dict[str, Json], old: Pointer, new: Pointer
    ) -> None:
        if "if" not in node:
            return  # then and else mean nothing without it
        if self.target == "draft-04":
            raise UnsupportedError("if does not exist in draft-04")
        for key in ("if", "then", "else"):
            if key in node:
                out[key] = self.schema(node[key], (*old, key), (*new, key))

    def exclusive_bounds(self, node: dict[str, Json], out: dict[str, Json]) -> None:
        """A numeric exclusive bound is a flag on ``minimum`` or ``maximum`` in draft-04."""
        for bound, exclusive, tighter in (
            ("minimum", "exclusiveMinimum", max),
            ("maximum", "exclusiveMaximum", min),
        ):
            limit = node.get(exclusive)
            if not isinstance(limit, (int, float)) or isinstance(limit, bool):
                continue
            inclusive = node.get(bound)
            # Both bounds given: the tighter one holds, and at a tie the exclusive one.
            if (
                isinstance(inclusive, (int, float))
                and not isinstance(inclusive, bool)
                and tighter(inclusive, limit) == inclusive
                and inclusive != limit
            ):
                continue
            out[bound] = limit
            out[exclusive] = True


def downgrade(schema: Json, target: OlderDraft) -> Json:
    """The schema rewritten for an older draft, accepting the same instances.

    Args:
        schema: A draft 2020-12 schema whose references all resolve inside it.
        target: The draft to rewrite for.

    Returns:
        A schema of the older draft in which every reference is a pointer from the root.

    Raises:
        UnsupportedError: The older draft cannot express the schema.
    """
    match target:
        case "draft-04" | "draft-07":
            return _Downgrade(schema, target).run(schema)
        case _:
            assert_never(target)
