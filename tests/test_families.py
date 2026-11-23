"""The families of generated cases: their labels hold, and the corpus holds them as generated.

A label of a family is known by construction. These tests check what can be checked without an
inclusion checker, with ``subsumes_benchmark.validation``:

- **A label that is false**: the counterexample is valid under the schema whose instances must
  be accepted and not valid under the other, by both validators.
- **Every label of a small member**: from a finite set of instances with one instance of every
  class that the two schemas tell apart. The schemas of a family look only at which names an
  object has and of what type each value is, or only at the characters of a string, so a
  schema accepts all of such a class or none of it. A schema then subsumes the other exactly
  when it accepts every instance of the set that the other accepts.
"""

from collections.abc import Iterator, Mapping, Sequence
from itertools import product
from typing import assert_never, get_args

import pytest

from reading import CORPUS, read
from subsumes_benchmark import Json
from subsumes_benchmark.compare.downgrade import OlderDraft, downgrade
from subsumes_benchmark.compare.tasks import Direction
from subsumes_benchmark.families import (
    Member,
    Sizes,
    coprime_counters,
    members,
    nth_from_end,
    pigeonhole,
    product_of_choices,
    split_order,
    tagged_unions,
)
from subsumes_benchmark.validation import is_valid, is_valid_to_another, validator

COLLECTION = CORPUS / "wolflein2026" / "scaling-families"

# What is no object and no string: every schema of a family rejects these.
OTHERS: Sequence[Json] = (None, True, 0, 0.5, [])

# A value of each type that a family tells apart: a string, a boolean, and neither.
VALUES: Sequence[Json] = ("", True, 0)

MEMBERS = list(members(Sizes.corpus()))


def objects(values: Mapping[str, Sequence[Json]]) -> Iterator[Json]:
    """Every object with some of the names, each with one of the values of its name."""
    names = list(values)
    # The first choice of every name is to leave it out.
    for chosen in product(*(range(len(values[name]) + 1) for name in names)):
        yield {name: values[name][at - 1] for name, at in zip(names, chosen, strict=True) if at}


def strings(alphabet: str, longest: int) -> Iterator[Json]:
    """Every string of the characters, of at most the length."""
    for length in range(longest + 1):
        for characters in product(alphabet, repeat=length):
            yield "".join(characters)


def decided(member: Member, instances: Iterator[Json]) -> tuple[bool, bool]:
    """Whether ``a`` subsumes ``b``, and ``b`` ``a``, as far as the instances tell."""
    a, b = validator(member.a), validator(member.b)
    a_subsumes_b = b_subsumes_a = True
    for instance in [*instances, *OTHERS]:
        in_a, in_b = a.is_valid(instance), b.is_valid(instance)
        a_subsumes_b &= in_a or not in_b
        b_subsumes_a &= in_b or not in_a
    return a_subsumes_b, b_subsumes_a


def every_class(member: Member) -> Iterator[Json]:
    """An instance of every class of instances that the two schemas of the member tell apart.

    - ``split-order``: an object with any of the shapes' names, ``extra`` and one other name,
      each a string, a boolean or neither.
    - ``product-of-choices``: an object with any of the names that a choice is between.
    - ``nth-from-end``: a string of ``a``, ``b`` and ``c``. Whether such a string matches
      either pattern depends only on whether it has a ``c``, on its length up to n + 2 and on
      its last n + 2 characters, so it is the class of a string of at most n + 3 characters.
    - ``coprime-counters``: a string of ``a`` of every length up to 2pq + 1, which has every
      remainder of a division by 2pq, and short strings with a ``b``.
    - ``tagged-unions``: an object with a ``kind`` of each tag, of another string or of a
      number, and any of the fields and one other name, each a string, a boolean or neither.
    - ``pigeonhole``: an object with any of the properties ``true``, for holes + 1 pigeons or
      for the twin's as many pigeons as holes; a property that is not ``true`` is the same to
      the schemas as one that is not there.
    """
    match member.family:
        case "split-order":
            names = [chr(ord("a") + index) for index in range(member.sizes["shapes"])]
            return objects(dict.fromkeys([*names, "extra", "other"], VALUES))
        case "product-of-choices":
            choices = range(member.sizes["choices"])
            return objects({f"{side}{index}": [0] for index in choices for side in "xy"})
        case "nth-from-end":
            return strings("abc", member.sizes["n"] + 3)
        case "coprime-counters":
            longest = 2 * member.sizes["p"] * member.sizes["q"] + 1
            return iter([*("a" * length for length in range(longest + 1)), *strings("ab", 3)])
        case "tagged-unions":
            tags = [f"k{index}" for index in range(member.sizes["kinds"])]
            fields = [f"f{index}" for index in range(member.sizes["fields"])]
            return objects({"kind": [*tags, "k", 0]} | dict.fromkeys([*fields, "other"], VALUES))
        case "pigeonhole":
            holes = member.sizes["holes"]
            pigeons = holes if member.twin else holes + 1
            names = [f"p{pigeon}h{hole}" for pigeon in range(pigeons) for hole in range(holes)]
            return objects({name: [True] for name in names})
        case _:
            assert_never(member.family)


# Members small enough for ``every_class``: of every family, and of every depth of split-order.
SMALL = [
    *(
        member
        for shapes in (1, 2)
        for depth in (1, 2, 3, 4)
        for member in split_order(shapes, depth)
    ),
    *(member for choices in (1, 2, 3, 4) for member in product_of_choices(choices)),
    *(member for n in (1, 2, 3) for member in nth_from_end(n)),
    *(member for p, q in ((2, 3), (3, 5)) for member in coprime_counters(p, q)),
    *(
        member
        for kinds, fields in ((1, 1), (2, 2), (3, 2))
        for member in tagged_unions(kinds, fields)
    ),
    *(member for holes in (1, 2, 3) for member in pigeonhole(holes)),
]


@pytest.mark.parametrize("member", SMALL, ids=lambda member: member.name)
def test_the_labels_of_a_small_member_hold(member: Member) -> None:
    assert decided(member, every_class(member)) == (member.a_subsumes_b, member.b_subsumes_a)


@pytest.mark.parametrize(
    ("member", "direction"),
    [(member, direction) for member in MEMBERS for direction in member.counterexamples],
    ids=lambda value: value.name if isinstance(value, Member) else value,
)
def test_a_counterexample_refutes_its_label(member: Member, direction: Direction) -> None:
    instance = member.counterexamples[direction]
    if direction == "a_subsumes_b":
        accepting, narrower = member.a, member.b
    else:
        accepting, narrower = member.b, member.a
    assert isinstance(accepting, dict | bool)
    assert isinstance(narrower, dict | bool)
    assert is_valid(instance, narrower)
    assert not is_valid(instance, accepting)
    assert is_valid_to_another(instance, narrower)
    assert not is_valid_to_another(instance, accepting)


def test_every_member_has_a_twin_whose_answer_flips() -> None:
    by_name = {member.name: member for member in MEMBERS}
    assert len(by_name) == len(MEMBERS)
    twins = [member for member in MEMBERS if member.twin]
    assert len(twins) * 2 == len(MEMBERS)
    for twin in twins:
        member = by_name[twin.name.removesuffix(".twin")]
        assert (member.a_subsumes_b, member.b_subsumes_a) == (True, True)
        assert False in (twin.a_subsumes_b, twin.b_subsumes_a)
        assert twin.family == member.family
        assert twin.sizes.keys() == member.sizes.keys()


@pytest.mark.parametrize("target", get_args(OlderDraft.__value__))
def test_a_checker_of_an_older_draft_can_be_asked(target: OlderDraft) -> None:
    # The runner rewrites the schemas for such a checker, and every family keeps to keywords
    # that it can rewrite.
    for member in MEMBERS:
        downgrade(member.a, target)
        downgrade(member.b, target)


def test_the_corpus_holds_every_member_and_nothing_else() -> None:
    found = {path.stem: read(path) for path in COLLECTION.glob("*.json")}
    assert sorted(found) == sorted(member.name for member in MEMBERS)
    for member in MEMBERS:
        case = found[member.name]
        assert isinstance(case, dict)
        assert case["a"] == member.a
        assert case["b"] == member.b
        assert (case["a_subsumes_b"], case["b_subsumes_a"]) == (
            member.a_subsumes_b,
            member.b_subsumes_a,
        )
        assert case["generated"] == member.generated.model_dump()
        assert "upstream" not in case
