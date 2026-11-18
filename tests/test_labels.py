"""The labels that can be checked by validating instances hold.

When ``b`` only lists its instances, ``a`` subsumes it exactly when every one of them is
valid under ``a``. That checks the label without an inclusion checker, with
patterns matched as ECMA-262 does with the ``u`` flag and ``format`` asserted.
"""

import json
from typing import TYPE_CHECKING

import pytest

from reading import Case, case, cases, constants, patterns
from subsumes_benchmark.validation import is_valid, pattern_error

if TYPE_CHECKING:
    from subsumes_benchmark import Json

CATEGORIES = frozenset({"valid", "nonvalid", "unions", "reflexive", "universal", "unsatisfiable"})

# Instances valid under b and not under a, for the labels that overrides.json corrects to
# false in cases where b does not list its instances.
COUNTEREXAMPLES: dict[str, Json] = {
    "handwritten-sc/bool.7.eq1.sub.eq2": "aa\nbb",
    "handwritten-sc/bool.7.strong.sub.eq2": "aaa\nbb",
    "mergeallof/items_merges_additionalItems.orig_not_merge": [{}, {"name": "foo\nbar"}],
    "mergeallof/module_merges_pattern_using_allOf.orig_not_merge": "fdsaf\nabba",
}


@pytest.mark.parametrize(("case_id", "instance"), COUNTEREXAMPLES.items())
def test_counterexample_refutes_the_inclusion(case_id: str, instance: Json) -> None:
    found = case(case_id)
    assert found.a_subsumes_b is False
    assert is_valid(instance, found.b)
    assert not is_valid(instance, found.a)


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
    assert checked > 5000


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


def test_the_test_suite_asks_no_question_twice() -> None:
    seen: dict[str, str] = {}
    twice = []
    for group in suite_cases().values():
        for found in group.values():
            key = json.dumps([found.a, found.b], sort_keys=True)
            if key in seen:
                twice.append((seen[key], found.id))
            seen[key] = found.id
    assert twice == []


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
