"""The labels that can be checked by validating instances hold.

When ``b.json`` only lists its instances, ``a.json`` subsumes it exactly when every one of
them is valid under ``a.json``. That checks the label without an inclusion checker, with
patterns matched in the Rust regex dialect.
"""

from typing import TYPE_CHECKING

import pytest

from reading import case, cases, constants, patterns, referenced_documents, resources, uses_format
from validation import is_valid, pattern_error

if TYPE_CHECKING:
    from subsumes_benchmark import Json

# Instances valid under b.json and not under a.json, for the labels that overrides.toml
# corrects to false in cases where b.json does not list its instances.
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


@pytest.mark.slow
def test_label_holds_where_b_lists_its_instances() -> None:
    checked = 0
    wrong = {}
    for found in cases():
        if found.a_subsumes_b is None:
            continue
        instances = constants(found.b)
        if instances is None:
            continue
        a = found.a
        if uses_format(a):
            continue
        checked += 1
        computed = all(is_valid(instance, a) for instance in instances)
        if computed != found.a_subsumes_b:
            wrong[found.id] = computed
    assert wrong == {}
    assert checked > 2000


@pytest.mark.slow
def test_labelled_case_has_only_patterns_of_the_rust_regex_dialect() -> None:
    rejected_documents = {
        url for url, document in resources().items() if any(map(pattern_error, patterns(document)))
    }
    wrong = []
    for found in cases():
        if found.claims_nothing:
            continue
        a, b = found.a, found.b
        used = patterns(a) | patterns(b)
        reached = referenced_documents(a) | referenced_documents(b)
        if any(map(pattern_error, used)) or reached & rejected_documents:
            wrong.append(found.id)
    assert wrong == []
