"""The labels that can be checked by validating instances hold.

When ``b`` only lists its instances, ``a`` subsumes it exactly when every one of them is
valid under ``a``. That checks the label without an inclusion checker, with
patterns matched as ECMA-262 does with the ``u`` flag and ``format`` asserted.
"""

import json
from typing import TYPE_CHECKING, assert_never

import pytest

from reading import Case, case, cases, constants, patterns
from subsumes_benchmark.validation import is_valid, pattern_error

if TYPE_CHECKING:
    from subsumes_benchmark import Json
    from subsumes_benchmark.compare.tasks import Direction

CATEGORIES = frozenset({"valid", "nonvalid", "unions", "reflexive", "universal", "unsatisfiable"})

# Instances that refute an inclusion, for the labels that overrides.json corrects to false in
# cases where the narrower schema does not list its instances. A case that stands for two
# upstream cases has the label of the other one as the label of its other direction.
COUNTEREXAMPLES: dict[tuple[str, Direction], Json] = {
    ("handwritten-sc/bool.7.eq1.sub.eq2", "a_subsumes_b"): "aa\nbb",
    ("handwritten-sc/bool.7.eq2.notsub.strong", "b_subsumes_a"): "aaa\nbb",
    ("mergeallof/items_merges_additionalItems.merge_not_orig", "b_subsumes_a"): [
        {},
        {"name": "foo\nbar"},
    ],
    ("mergeallof/module_merges_pattern_using_allOf.merge_not_orig", "b_subsumes_a"): "fdsaf\nabba",
}


@pytest.mark.parametrize(("question", "instance"), COUNTEREXAMPLES.items())
def test_counterexample_refutes_the_inclusion(
    question: tuple[str, Direction], instance: Json
) -> None:
    case_id, direction = question
    found = case(case_id)
    assert found.note is not None
    match direction:
        case "a_subsumes_b":
            label, accepting, narrower = found.a_subsumes_b, found.a, found.b
        case "b_subsumes_a":
            label, accepting, narrower = found.b_subsumes_a, found.b, found.a
        case _:
            assert_never(direction)
    assert label is False
    assert is_valid(instance, narrower)
    assert not is_valid(instance, accepting)


def test_label_holds_where_b_lists_its_instances() -> None:
    checked = 0
    wrong = {}
    for found in cases():
        if found.a_subsumes_b is None:
            continue
        instances = constants(found.b)
        if instances is None:
            continue
        checked += 1
        computed = all(is_valid(instance, found.a) for instance in instances)
        if computed != found.a_subsumes_b:
            wrong[found.id] = computed
    assert wrong == {}
    assert checked > 4000


def test_labelled_case_has_only_valid_patterns() -> None:
    wrong = []
    for found in cases():
        if found.claims_nothing:
            continue
        # The documents a schema references are embedded in it, so these are all its patterns.
        if any(map(pattern_error, patterns(found.a) | patterns(found.b))):
            wrong.append(found.id)
    assert wrong == []


def suite_cases() -> dict[str, dict[str, Case]]:
    """The cases built from the test suite, by test case of the suite and then by kind."""
    groups: dict[str, dict[str, Case]] = {}
    for found in cases():
        if found.collection != "json-schema-test-suite":
            continue
        parts = found.id.split("/")
        at = next(i for i, part in enumerate(parts) if part in CATEGORIES)
        groups.setdefault("/".join(parts[:at]), {})["/".join(parts[at:])] = found
    return groups


def test_no_two_cases_hold_the_same_two_schemas() -> None:
    # Not in either order: the other direction of a case is a question of that case.
    seen: dict[frozenset[str], str] = {}
    twice = []
    listed = []
    for found in cases():
        key = frozenset(json.dumps(schema, sort_keys=True) for schema in (found.a, found.b))
        if key in seen:
            twice.append((seen[key], found.id))
        seen[key] = found.id
        if found.upstream in found.duplicates or len(set(found.duplicates)) != len(
            found.duplicates
        ):
            listed.append(found.id)
    assert twice == []
    assert listed == []
    assert sum(1 for found in cases() if found.duplicates) > 4000


def test_a_schema_with_its_negation_accepts_everything_or_nothing() -> None:
    # ``universal`` and ``unsatisfiable`` hold whatever the schema is, as long as the negated
    # schema inside them is the same schema. The instances of the test case tell.
    wrong = []
    checked = 0
    for group in suite_cases().values():
        instances = [
            constant["const"]
            for kind, found in group.items()
            if kind.startswith("valid/") and isinstance(constant := found.b, dict)
        ]
        for kind, expected in (("universal", True), ("unsatisfiable", False)):
            found = group.get(kind)
            if found is None or found.claims_nothing:
                continue
            checked += len(instances)
            if any(is_valid(instance, found.b) != expected for instance in instances):
                wrong.append(found.id)
    assert wrong == []
    assert checked > 2500
