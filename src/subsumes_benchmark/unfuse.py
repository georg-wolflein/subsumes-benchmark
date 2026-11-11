"""Splitting a fused test of the inclusion artifact back into its two schemas.

The artifact stores each test as one document ``{"allOf": [S1, {"not": S2}]}``, which is
satisfiable exactly when S1 is not included in S2. Both sides' definitions are hoisted to the
top level under ``definitions1`` to ``definitions4`` (or a shared ``definitions`` in older
runs), every other pointer of a side is prefixed with its path in the fused document
(``#/allOf/0/...``, ``#/allOf/1/not/...``), and a top-level ``anyOf`` lists every hoisted
definition so that none is unreachable. This is the inverse of
``SchemaProcessorLib.combineSchemas`` in the artifact's Scala source.
"""

import re
from typing import TYPE_CHECKING

from subsumes_benchmark.convert import HOISTED_GROUPS, VERBATIM_KEYWORDS, ConversionError

if TYPE_CHECKING:
    from subsumes_benchmark import Json

# The older pipeline hoisted a shared, un-renamed "definitions" instead.
FUSED_GROUPS = (*HOISTED_GROUPS, "definitions")


def collect_refs(node: Json, out: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            collect_refs(item, out)
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            out.append(ref)
        for key, value in node.items():
            if key not in VERBATIM_KEYWORDS:
                collect_refs(value, out)


def strip_fused_path(node: Json, own: str) -> Json:
    """Undo the artifact's rewrite of a side's references to ``#/allOf/0/...`` paths.

    The artifact prefixes every non-definition pointer of a side with the side's path in
    the fused document, so stripping that prefix once restores the original pointer.
    """
    if isinstance(node, list):
        return [strip_fused_path(item, own) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Json] = {}
    for key, value in node.items():
        if key == "$ref" and isinstance(value, str):
            if value == own:
                value = "#"
            elif value.startswith(own + "/"):
                value = "#" + value[len(own) :]
        elif key not in VERBATIM_KEYWORDS:
            value = strip_fused_path(value, own)
        out[key] = value
    return out


def groups_reachable(body: Json, groups: dict[str, Json]) -> list[str]:
    """The hoisted definition groups a side references, transitively."""
    needed: list[str] = []
    pending = [body]
    while pending:
        refs: list[str] = []
        collect_refs(pending.pop(), refs)
        for ref in refs:
            match = re.match(r"^#/(definitions[1-4]?)(/|$)", ref)
            if match and match.group(1) in groups and match.group(1) not in needed:
                needed.append(match.group(1))
                pending.append(groups[match.group(1)])
    return sorted(needed)


def unfuse(doc: Json) -> tuple[Json, Json, set[str]]:
    """Split a fused document into ``(S1, S2)`` and the notes on what was dropped."""
    notes: set[str] = set()
    pair = doc.get("allOf") if isinstance(doc, dict) else None
    if not isinstance(doc, dict) or not isinstance(pair, list) or len(pair) != 2:
        raise ConversionError("not an allOf pair")
    s1, wrapped = pair
    if not (isinstance(wrapped, dict) and list(wrapped) == ["not"]):
        raise ConversionError("second conjunct is not a negation")
    s2 = wrapped["not"]
    extra = set(doc) - {"allOf", "anyOf", *FUSED_GROUPS}
    if extra:
        raise ConversionError(f"unexpected top-level keys {sorted(extra)}")
    members = doc.get("anyOf")
    if isinstance(members, list):
        if all(isinstance(m, dict) and list(m) == ["$ref"] for m in members):
            # An older run of the artifact's pipeline listed the hoisted definitions as a
            # plain disjunction, which does constrain the fused schema. It cannot turn a
            # non-inclusion into an inclusion, and the affected dataset carries no
            # "unsat" label, so no label depends on it.
            notes.add("top-level anyOf of plain definition references dropped")
        else:
            for i in range(0, len(members), 2):
                first, second = members[i], members[i + 1] if i + 1 < len(members) else None
                if not (
                    isinstance(first, dict) and list(first) == ["$ref"] and second == {"not": first}
                ):
                    raise ConversionError(
                        "top-level anyOf is neither the tautology nor the reference list "
                        "the artifact emits"
                    )
            # fixAndMigrate in the artifact adds (ref or not ref) per hoisted definition
            # so that every definition stays reachable; it carries no constraint.
            notes.add("top-level tautology anyOf dropped")
    elif members is not None:
        raise ConversionError("top-level anyOf is not an array")
    groups = {name: doc[name] for name in FUSED_GROUPS if name in doc}

    def side(body: Json, own: str) -> Json:
        body = strip_fused_path(body, own)
        if not isinstance(body, dict):
            return body
        for name in groups_reachable(body, groups):
            body[name] = strip_fused_path(groups[name], own)
        return body

    return side(s1, "#/allOf/0"), side(s2, "#/allOf/1/not"), notes
