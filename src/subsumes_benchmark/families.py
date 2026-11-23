"""Families of generated cases that grow with a size, whose answers are known by construction.

A family is a way to build two schemas from one or two sizes, so that a checker can be
measured on where it stops, or answers wrongly, as the cases grow, and not only on whether
it solves one of them. Every member has a twin: a near-copy whose answer flips in at least
one direction, so that a checker that always says yes does not solve a family.

- ``split-order``: the ``oneOf`` of closed object shapes against the same shapes with the
  keywords of each spread over nested ``allOf``. A checker that splits a disjunction in a
  poor order explores every combination of the branches.
- ``product-of-choices``: a conjunction of n choices between two required properties
  against the same said through De Morgan's laws, in the reverse order. Written as a
  disjunction of conjunctions, either side has 2^n terms.
- ``nth-from-end``: the strings over ``a`` and ``b`` whose (n+1)-th character from the end
  is ``a``, as two patterns. The smallest deterministic automaton has 2^(n+1) states.
- ``coprime-counters``: strings of ``a`` whose length is a multiple of p and of q, against
  those whose length is a multiple of pq, for coprime p and q.
- ``tagged-unions``: a ``oneOf`` of object kinds told apart by the ``const`` of a ``kind``
  property, against the ``anyOf`` of the same kinds, which is how discriminated unions are
  generated in practice.
- ``pigeonhole``: whether pigeons fit into holes, one to a hole, as an object of boolean
  properties, against ``false``. Every method that splits cases takes time exponential in
  the number of holes to see that p+1 pigeons do not fit into p holes (Haken 1985).

Every schema keeps to keywords that draft-04 has where the family allows, so that a checker
that reads an older draft can be asked too, through the rewriting of the comparison.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import Self

from subsumes_benchmark import Json
from subsumes_benchmark.generated.case import (
    ConstructionLabel,
    CounterexampleLabel,
    Family,
    FromGenerator,
)
from subsumes_benchmark.generated.result import Direction

# Where the generator lives in the repository, for the manifest of the corpus.
PATH = "src/subsumes_benchmark/families.py"


@dataclass(frozen=True)
class Member:
    """One case of a family: two schemas, their labels, and what refutes a label ``false``.

    ``sizes`` are the sizes of the member in the order its name gives them. A twin is the
    near-copy of the member of the same sizes whose answer flips in at least one direction.
    ``counterexamples`` has an instance for every label that is ``false``: valid under the
    schema whose instances must be accepted, and not valid under the other.
    """

    family: Family
    sizes: Mapping[str, int]
    twin: bool
    a: Json
    b: Json
    a_subsumes_b: bool
    b_subsumes_a: bool
    counterexamples: Mapping[Direction, Json] = field(default_factory=dict)

    def __post_init__(self) -> None:
        refuted = set(self.counterexamples)
        false: set[Direction] = {
            direction
            for direction, label in (
                ("a_subsumes_b", self.a_subsumes_b),
                ("b_subsumes_a", self.b_subsumes_a),
            )
            if not label
        }
        if refuted != false:
            raise ValueError(f"{self.name}: a counterexample for every false label, and no other")
        if self.twin == (not false):
            raise ValueError(f"{self.name}: a twin flips a label, and a member flips none")

    @property
    def generated(self) -> FromGenerator:
        """What a case of the corpus says it was built from."""
        return FromGenerator(
            kind="generator", family=self.family, sizes=dict(self.sizes), twin=self.twin
        )

    def label(self, direction: Direction) -> ConstructionLabel | CounterexampleLabel:
        """The label of a case of the corpus in one direction, with what shows it."""
        if direction in self.counterexamples:
            instance = self.counterexamples[direction]
            return CounterexampleLabel(kind="counterexample", answer=False, instance=instance)
        return ConstructionLabel(kind="construction", answer=True)

    @property
    def name(self) -> str:
        """The name of the case: the family, every size after its knob, and ``twin`` for one."""
        sizes = (f"{knob}{size}" for knob, size in self.sizes.items())
        return ".".join([self.family, *sizes, *(["twin"] if self.twin else [])])


@dataclass(frozen=True)
class Sizes:
    """The sizes that the corpus builds of each family."""

    split_order_shapes: Sequence[int]
    split_order_depths: Sequence[int]
    choices: Sequence[int]
    nth_from_end: Sequence[int]
    coprimes: Sequence[tuple[int, int]]
    tagged_kinds: Sequence[int]
    tagged_fields: Sequence[int]
    holes: Sequence[int]

    @classmethod
    def corpus(cls) -> Self:
        """The sizes of the corpus.

        The largest of each family is beyond every checker of the comparison, or is as large
        as a family gets without making the corpus large; ``docs/construction.md`` says which
        checker stops where. A size beyond subsumes costs its CI about 0.5 to 2 seconds a
        question, until its budget runs out, so a family goes on a few sizes beyond it and
        no further.
        """
        return cls(
            split_order_shapes=(2, 4, 6, 8, 12, 16),
            split_order_depths=(1, 2, 3, 4),
            choices=(4, 8, 12, 16, 24, 32, 48, 64),
            nth_from_end=(2, 4, 6, 8, 10, 12, 14, 16, 18, 20),
            coprimes=((2, 3), (3, 5), (5, 7), (7, 11), (11, 13), (13, 17)),
            tagged_kinds=(5, 10, 20, 40, 80),
            tagged_fields=(5, 10, 30),
            holes=(2, 3, 4, 5, 6, 7, 8),
        )


def members(sizes: Sizes) -> Iterator[Member]:
    """Every member of every family at the given sizes, each followed by its twin."""
    for shapes in sizes.split_order_shapes:
        for depth in sizes.split_order_depths:
            yield from split_order(shapes, depth)
    for choices in sizes.choices:
        yield from product_of_choices(choices)
    for n in sizes.nth_from_end:
        yield from nth_from_end(n)
    for p, q in sizes.coprimes:
        yield from coprime_counters(p, q)
    for kinds in sizes.tagged_kinds:
        for fields in sizes.tagged_fields:
            yield from tagged_unions(kinds, fields)
    for holes in sizes.holes:
        yield from pigeonhole(holes)


# --------------------------------------------------------------------------- split order


def _shape_names(shapes: int) -> Sequence[str]:
    """The names of the shapes, one letter each: ``a``, ``b``, ``c`` and so on."""
    if not 0 < shapes <= 26:
        raise ValueError(f"split-order: {shapes} shapes, and there are 26 letters")
    return [chr(ord("a") + index) for index in range(shapes)]


def _closed_shape(name: str) -> Json:
    """One closed schema: the required string ``name``, an optional boolean ``extra``, no more."""
    return {
        "type": "object",
        "properties": {name: {"type": "string"}, "extra": {"type": "boolean"}},
        "required": [name],
        "additionalProperties": False,
    }


def _nested_shape(name: str, depth: int, *, extra: bool) -> Json:
    """The same shape with its keywords spread over ``depth`` levels of ``allOf``.

    The property names that the shape allows are those that its ``patternProperties`` match,
    next to ``additionalProperties: false``: ``name`` and, if ``extra``, ``extra``.
    """
    allowed = [name, *(["extra"] if extra else [])]
    typed: dict[str, Json] = {"type": "object"}
    properties: dict[str, Json] = {
        "properties": {name: {"type": "string"}, "extra": {"type": "boolean"}}
    }
    required: dict[str, Json] = {"required": [name]}
    closed: dict[str, Json] = {
        "patternProperties": {f"^{allowed_name}$": True for allowed_name in allowed},
        "additionalProperties": False,
    }
    match depth:
        case 1:
            # One schema: what ``properties`` names is allowed too, so it names ``allowed``.
            one: dict[str, Json] = {name: {"type": "string"}, "extra": {"type": "boolean"}}
            return typed | {"properties": {key: one[key] for key in allowed}} | required | closed
        case 2:
            return {"allOf": [typed | properties | required, closed]}
        case 3:
            return {"allOf": [{"allOf": [typed | properties, required]}, closed]}
        case 4:
            return {"allOf": [{"allOf": [{"allOf": [typed, properties]}, required]}, closed]}
        case _:
            raise ValueError(f"split-order: depth {depth}, and there are depths 1 to 4")


def split_order(shapes: int, depth: int) -> Iterator[Member]:
    """``b`` is the ``oneOf`` of closed shapes, ``a`` the same shapes nested ``depth`` deep.

    The shapes exclude each other, so both are their union, and each subsumes the other. The
    twin's ``a`` does not allow ``extra`` in the last shape.
    """
    names = _shape_names(shapes)
    b: Json = {"oneOf": [_closed_shape(name) for name in names]}
    sizes = {"shapes": shapes, "depth": depth}
    yield Member(
        "split-order",
        sizes,
        twin=False,
        a={"oneOf": [_nested_shape(name, depth, extra=True) for name in names]},
        b=b,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    last = names[-1]
    yield Member(
        "split-order",
        sizes,
        twin=True,
        a={"oneOf": [_nested_shape(name, depth, extra=name != last) for name in names]},
        b=b,
        a_subsumes_b=False,
        b_subsumes_a=True,
        counterexamples={"a_subsumes_b": {last: "", "extra": True}},
    )


# --------------------------------------------------------------------------- product of choices


def _either(index: int) -> Json:
    return {"anyOf": [{"required": [f"x{index}"]}, {"required": [f"y{index}"]}]}


def _neither_missing(index: int) -> Json:
    """``_either`` through De Morgan's laws: not both of the two missing."""
    missing: list[Json] = [
        {"not": {"required": [f"x{index}"]}},
        {"not": {"required": [f"y{index}"]}},
    ]
    return {"not": {"allOf": missing}}


def product_of_choices(choices: int) -> Iterator[Member]:
    """``b`` requires one of ``x_i`` and ``y_i`` for every i, ``a`` says so in reverse order.

    The twin's ``a`` requires ``x0`` alone where it had the choice, so it accepts less.
    """
    b: Json = {"type": "object", "allOf": [_either(index) for index in range(choices)]}
    reverse = range(choices - 1, -1, -1)
    sizes = {"choices": choices}
    yield Member(
        "product-of-choices",
        sizes,
        twin=False,
        a={"type": "object", "allOf": [_neither_missing(index) for index in reverse]},
        b=b,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    narrowed = [
        {"required": ["x0"]} if index == 0 else _neither_missing(index) for index in reverse
    ]
    yield Member(
        "product-of-choices",
        sizes,
        twin=True,
        a={"type": "object", "allOf": narrowed},
        b=b,
        a_subsumes_b=False,
        b_subsumes_a=True,
        counterexamples={
            "a_subsumes_b": {"y0": True} | {f"x{index}": True for index in range(1, choices)}
        },
    )


# --------------------------------------------------------------------------- regular expressions


def _string(pattern: str) -> Json:
    return {"type": "string", "pattern": pattern}


def nth_from_end(n: int) -> Iterator[Member]:
    """Strings over ``a`` and ``b`` whose (n+1)-th character from the end is ``a``, twice.

    ``b`` writes it with character classes and ``a`` with groups, one repetition shorter and
    a group after it. The twin's ``a`` has the ``a`` one place further from the end, so
    neither schema subsumes the other.
    """
    if n < 1:
        raise ValueError(f"nth-from-end: n = {n}, and it is at least 1")
    b = _string(f"^[ab]*a[ab]{{{n}}}$")
    sizes = {"n": n}
    yield Member(
        "nth-from-end",
        sizes,
        twin=False,
        a=_string(f"^(a|b)*a(a|b){{{n - 1}}}(a|b)$"),
        b=b,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    yield Member(
        "nth-from-end",
        sizes,
        twin=True,
        a=_string(f"^(a|b)*a(a|b){{{n}}}(a|b)$"),
        b=b,
        a_subsumes_b=False,
        b_subsumes_a=False,
        counterexamples={"a_subsumes_b": "a" + "b" * n, "b_subsumes_a": "a" + "b" * (n + 1)},
    )


def _coprime(p: int, q: int) -> bool:
    while q:
        p, q = q, p % q
    return p == 1


def coprime_counters(p: int, q: int) -> Iterator[Member]:
    """``b`` takes strings of ``a`` whose length is a multiple of p and of q, ``a`` of pq.

    The twin's ``a`` takes multiples of 2pq, which leaves out the string of pq characters.
    """
    if not (1 < p < q and _coprime(p, q)):
        raise ValueError(f"coprime-counters: {p} and {q} are no coprime p < q above 1")
    b: Json = {
        "type": "string",
        "allOf": [{"pattern": f"^(a{{{p}}})*$"}, {"pattern": f"^(a{{{q}}})*$"}],
    }
    sizes = {"p": p, "q": q}
    yield Member(
        "coprime-counters",
        sizes,
        twin=False,
        a=_string(f"^(a{{{p * q}}})*$"),
        b=b,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    yield Member(
        "coprime-counters",
        sizes,
        twin=True,
        a=_string(f"^(a{{{2 * p * q}}})*$"),
        b=b,
        a_subsumes_b=False,
        b_subsumes_a=True,
        counterexamples={"a_subsumes_b": "a" * (p * q)},
    )


# --------------------------------------------------------------------------- tagged unions


def _kind(index: int, fields: int, *, first: str = "string") -> Json:
    """Kind ``index``: its tag, ``fields`` string fields of which it requires the first."""
    properties: dict[str, Json] = {"kind": {"const": f"k{index}"}}
    properties |= {
        f"f{field}": {"type": first if field == 0 else "string"} for field in range(fields)
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["kind", "f0"],
        "additionalProperties": False,
    }


def tagged_unions(kinds: int, fields: int) -> Iterator[Member]:
    """``b`` is the ``oneOf`` of the kinds, ``a`` their ``anyOf``.

    The tags exclude each other, so both are the union. The twin's ``a`` has an integer
    ``f0`` in the last kind, so neither schema subsumes the other.
    """
    b: Json = {"oneOf": [_kind(index, fields) for index in range(kinds)]}
    sizes = {"kinds": kinds, "fields": fields}
    yield Member(
        "tagged-unions",
        sizes,
        twin=False,
        a={"anyOf": [_kind(index, fields) for index in range(kinds)]},
        b=b,
        a_subsumes_b=True,
        b_subsumes_a=True,
    )
    last = kinds - 1
    retyped = [
        _kind(index, fields, first="integer" if index == last else "string")
        for index in range(kinds)
    ]
    yield Member(
        "tagged-unions",
        sizes,
        twin=True,
        a={"anyOf": retyped},
        b=b,
        a_subsumes_b=False,
        b_subsumes_a=False,
        counterexamples={
            "a_subsumes_b": {"kind": f"k{last}", "f0": ""},
            "b_subsumes_a": {"kind": f"k{last}", "f0": 0},
        },
    )


# --------------------------------------------------------------------------- pigeonhole


def _sits(pigeon: int, hole: int) -> str:
    """The property that says that the pigeon sits in the hole when it is ``true``."""
    return f"p{pigeon}h{hole}"


def _placements(pigeons: int, holes: int) -> Json:
    """Every pigeon sits in a hole, and no two pigeons in the same one."""
    somewhere: list[Json] = [
        {
            "anyOf": [
                {
                    "properties": {_sits(pigeon, hole): {"const": True}},
                    "required": [_sits(pigeon, hole)],
                }
                for hole in range(holes)
            ]
        }
        for pigeon in range(pigeons)
    ]
    alone: list[Json] = [
        {
            "not": {
                "properties": {
                    _sits(one, hole): {"const": True},
                    _sits(other, hole): {"const": True},
                },
                "required": [_sits(one, hole), _sits(other, hole)],
            }
        }
        for hole in range(holes)
        for one, other in combinations(range(pigeons), 2)
    ]
    return {"type": "object", "allOf": [*somewhere, *alone]}


def pigeonhole(holes: int) -> Iterator[Member]:
    """``b`` places ``holes + 1`` pigeons, which cannot be done, ``a`` is ``false``.

    So ``a`` subsumes ``b``. The twin places as many pigeons as there are holes, which can be
    done, so it does not; and ``b`` subsumes ``false`` either way.
    """
    if holes < 1:
        raise ValueError(f"pigeonhole: {holes} holes, and there is at least one")
    for pigeons in (holes + 1, holes):
        twin = pigeons == holes
        yield Member(
            "pigeonhole",
            {"holes": holes},
            twin=twin,
            a=False,
            b=_placements(pigeons, holes),
            a_subsumes_b=not twin,
            b_subsumes_a=True,
            counterexamples=(
                {"a_subsumes_b": {_sits(hole, hole): True for hole in range(holes)}} if twin else {}
            ),
        )
