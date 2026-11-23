"""The labels that upstream does not give: how they are derived, and that the corpus's hold."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest

import runs
from reading import CORPUS, ROOT, cases, read
from runs import Confirmation, a_witness
from subsumes_benchmark import Json
from subsumes_benchmark.build import Case, ConfigError, with_derived, write_case, write_json
from subsumes_benchmark.cases import read_case
from subsumes_benchmark.compare.derive import READ_DIFFERENTLY, Vote, decide, derive, refutes
from subsumes_benchmark.compare.tasks import read_unlabelled
from subsumes_benchmark.derived import Derivations, by_label, document, label
from subsumes_benchmark.generated.case import UpstreamCase
from subsumes_benchmark.generated.derived import Agreement, Counterexample, Derived
from subsumes_benchmark.generated.result import Direction
from subsumes_benchmark.validation import meaningless

TEXT: dict[str, Json] = {"type": "string"}
OPTIONAL: dict[str, Json] = {"type": ["string", "null"]}
NUMBER: dict[str, Json] = {"type": "number"}
OPTIONAL_NUMBER: dict[str, Json] = {"type": ["number", "null"]}


def a_case(a: Json, b: Json, note: str | None = None) -> UpstreamCase:
    built = Case("o/one/case", a, b, None, None, "x.json", note)
    return UpstreamCase.model_validate_json(json.dumps(built.document))


def yes(name: str, version: str = "1.0") -> Vote:
    return Vote(f"{name} {version}", name, "yes")


def no(name: str, counterexample: str | None = None) -> Vote:
    return Vote(f"{name} 1.0", name, "no", counterexample)


# --------------------------------------------------------------------------- what votes show


def test_a_counterexample_that_refutes_is_proof_whoever_gives_it() -> None:
    case = a_case(TEXT, OPTIONAL)
    assert decide(case, "a_subsumes_b", [no("one", "null")]) == Counterexample(counterexample=None)
    # It is proof against any number of checkers that say yes.
    votes = [yes("one"), yes("two"), no("three", "null")]
    assert decide(case, "a_subsumes_b", votes) == Counterexample(counterexample=None)
    # The shortest of several is kept, so that the same runs always give the same file.
    wider = a_case(TEXT, True)
    votes = [no("one", '{"a": 1}'), no("two", "[]"), no("three", "123")]
    assert decide(wider, "a_subsumes_b", votes) == Counterexample(counterexample=[])


def test_a_no_without_proof_shows_nothing_and_stands_against_a_yes() -> None:
    case = a_case(TEXT, OPTIONAL)
    for unproven in (None, "not an instance", '"valid under both"', "12"):
        votes = [yes("one"), yes("two"), no("three", unproven)]
        assert decide(case, "a_subsumes_b", votes) == "contradicted"


def test_an_instance_is_one_that_a_double_holds() -> None:
    wide: Json = {"type": "integer"}
    narrow: Json = {"type": "integer", "maximum": 9007199254740992}
    case = a_case(narrow, wide)
    # 2**53 + 1 is not a double, so what it shows depends on who reads it.
    assert decide(case, "a_subsumes_b", [no("one", "9007199254740993")]) == "contradicted"
    assert decide(case, "a_subsumes_b", [no("one", "NaN")]) == "contradicted"
    assert decide(case, "a_subsumes_b", [no("one", "9007199254740994")]) == Counterexample(
        counterexample=9007199254740994
    )


def test_two_checkers_that_say_yes_agree() -> None:
    case = a_case(OPTIONAL, TEXT)
    assert decide(case, "a_subsumes_b", [yes("two"), yes("one")]) == Agreement(
        checkers=["one 1.0", "two 1.0"]
    )
    assert decide(case, "a_subsumes_b", [yes("one")]) == "one yes"
    # Two versions of a checker are one voice, and so are its variants, which share a name.
    assert decide(case, "a_subsumes_b", [yes("one"), yes("one", "2.0")]) == "one yes"
    assert decide(case, "a_subsumes_b", []) == "no answer"


@pytest.mark.parametrize(
    "narrow",
    [
        {"type": "string", "pattern": "^a"},
        {"type": "string", "format": "date"},
        {"type": "object", "patternProperties": {"^a": True}},
    ],
)
def test_checkers_do_not_agree_on_what_they_read_in_their_own_ways(narrow: Json) -> None:
    case = a_case(TEXT, narrow)
    assert READ_DIFFERENTLY & set(case.features)
    assert decide(case, "a_subsumes_b", [yes("one"), yes("two")]) == "read differently"
    # A counterexample is held against the schemas as the corpus reads them, so it still counts.
    assert decide(case, "b_subsumes_a", [no("one", '"b"')]) == Counterexample(counterexample="b")


@pytest.mark.parametrize(
    "schema",
    [
        {"pattern": r"^4\-"},  # not valid in ECMA-262 with the u flag
        {"patternProperties": {"a{": True}},
        {"format": "int32"},  # none of draft 2020-12
        {"$defs": {"unused": {"format": "color"}}},
    ],
)
def test_nothing_is_derived_for_a_schema_without_a_meaning(schema: Json) -> None:
    assert meaningless(schema) is not None
    case = a_case(True, schema)
    assert decide(case, "a_subsumes_b", [yes("one"), yes("two")]) == "no meaning"
    assert decide(case, "b_subsumes_a", [no("one", "12")]) == "no meaning"


def test_a_label_does_not_hinge_on_digits_that_a_double_does_not_hold() -> None:
    # 2**63 - 1 is no double: read as one, it is 2**63, and then the two schemas are the same.
    exact_bound: Json = {"type": "integer", "maximum": 9223372036854775807}
    rounded_bound: Json = {"type": "integer", "maximum": 9.223372036854776e18}
    case = a_case(exact_bound, rounded_bound)
    assert decide(case, "a_subsumes_b", [no("one", "9223372036854775808")]) == "contradicted"
    assert decide(case, "b_subsumes_a", [yes("one"), yes("two")]) == "read differently"
    # An instance that refutes however the bound is read still does.
    wide: Json = {"type": "integer"}
    assert decide(
        a_case(exact_bound, wide), "a_subsumes_b", [no("one", "18446744073709551616")]
    ) == (Counterexample(counterexample=18446744073709551616))


def test_a_case_that_an_override_lists_keeps_the_labels_of_the_override() -> None:
    case = a_case(TEXT, OPTIONAL, note="Upstream's label does not hold.")
    assert decide(case, "a_subsumes_b", [no("one", "null")]) == "overridden"
    assert decide(case, "b_subsumes_a", [yes("one"), yes("two")]) == "overridden"


def test_a_schema_of_draft_2020_12_has_a_meaning() -> None:
    schema: Json = {"pattern": r"^\d+$", "format": "date-time", "properties": {"format": True}}
    assert meaningless(schema) is None


def test_a_question_asked_the_other_way_swaps_the_schemas() -> None:
    case = a_case(OPTIONAL, TEXT)
    assert decide(case, "b_subsumes_a", [no("one", "null")]) == Counterexample(counterexample=None)
    assert refutes(None, TEXT, OPTIONAL)
    assert not refutes(None, OPTIONAL, TEXT)


# --------------------------------------------------------------------------- the file


def a_corpus(folder: Path, cases: Sequence[Case]) -> Path:
    for case in cases:
        write_case(folder, case)
    return folder


def write_answers(
    folder: Path,
    label: str,
    answers: Sequence[tuple[str, Direction, Literal["yes", "no"], str | None]],
    confirmation: Confirmation = "confirmed",
) -> Path:
    """A run of the checker with these answers, a no with its counterexample as JSON text."""
    results = [
        runs.a_result(
            case,
            answer,
            None,
            direction=direction,
            witness=None if given is None else a_witness(confirmation, json.loads(given)),
        )
        for case, direction, answer, given in answers
    ]
    runs.write(folder, runs.a_run(folder.name, label), results)
    return folder


def open_case(case_id: str, a: Json, b: Json, a_subsumes_b: bool | None = None) -> Case:
    return Case(case_id, a, b, a_subsumes_b, None, "x.json")


def test_runs_are_derived_into_the_file_and_a_later_run_adds_to_it(tmp_path: Path) -> None:
    corpus = a_corpus(
        tmp_path / "corpus",
        [
            open_case("o/one/narrower", OPTIONAL, TEXT),
            open_case("o/one/wider", NUMBER, OPTIONAL_NUMBER),
            open_case("o/one/open", TEXT, True),
            open_case("o/one/known", TEXT, TEXT, a_subsumes_b=True),
        ],
    )
    file = tmp_path / "derived.json"
    first = write_answers(
        tmp_path / "first",
        "One",
        [
            ("o/one/narrower", "a_subsumes_b", "yes", None),
            ("o/one/narrower", "b_subsumes_a", "no", "null"),
            ("o/one/wider", "a_subsumes_b", "no", "null"),
            ("o/one/open", "a_subsumes_b", "yes", None),
            # An answer to a question that has a label is not read.
            ("o/one/known", "a_subsumes_b", "no", "12"),
        ],
    )
    second = write_answers(
        tmp_path / "second", "Two", [("o/one/narrower", "a_subsumes_b", "yes", None)]
    )
    derive(corpus, file, [first])
    refuted = {"counterexample": None}
    assert read(file) == {
        "$schema": "./schemas/derived.schema.json",
        "cases": {
            "o/one/narrower": {"b_subsumes_a": refuted},
            "o/one/wider": {"a_subsumes_b": refuted},
        },
    }
    # The second checker makes an agreement of the first one's yes.
    derive(corpus, file, [first, second])
    agreed = {"checkers": ["One 1.0", "Two 1.0"]}
    expected = {
        "o/one/narrower": {"a_subsumes_b": agreed, "b_subsumes_a": refuted},
        "o/one/wider": {"a_subsumes_b": refuted},
    }
    assert read(file) == {"$schema": "./schemas/derived.schema.json", "cases": expected}
    # What the file holds is kept when a run that showed it is not read again, and reading
    # the same runs again changes nothing.
    text = file.read_text(encoding="utf-8")
    derive(corpus, file, [second])
    assert file.read_text(encoding="utf-8") == text
    derive(corpus, file, [first, second])
    assert file.read_text(encoding="utf-8") == text


def test_a_counterexample_replaces_the_agreement_it_refutes(tmp_path: Path) -> None:
    corpus = a_corpus(tmp_path / "corpus", [open_case("o/one/wider", TEXT, OPTIONAL)])
    file = tmp_path / "derived.json"
    entry = Derived(a_subsumes_b=Agreement(checkers=["One 1.0", "Two 1.0"]))
    Derivations.write(file, {"o/one/wider": entry})
    later = write_answers(
        tmp_path / "later", "Three", [("o/one/wider", "a_subsumes_b", "no", "null")]
    )
    derive(corpus, file, [later])
    assert Derivations.read(file).cases == {
        "o/one/wider": Derived(a_subsumes_b=Counterexample(counterexample=None))
    }


def test_a_counterexample_is_held_against_the_schemas_whatever_the_run_made_of_it(
    tmp_path: Path,
) -> None:
    corpus = a_corpus(
        tmp_path / "corpus",
        [open_case("o/one/wider", TEXT, OPTIONAL), open_case("o/one/same", TEXT, TEXT)],
    )
    file = tmp_path / "derived.json"
    answers: Sequence[tuple[str, Direction, Literal["yes", "no"], str | None]] = [
        ("o/one/wider", "a_subsumes_b", "no", "null"),
        ("o/one/same", "a_subsumes_b", "no", "null"),
    ]
    # The validator of the run did not look at the first, and is recorded as confirming the
    # second, which is none: the two validators here are asked about both.
    unchecked = write_answers(tmp_path / "unchecked", "One", answers[:1], "unchecked")
    confirmed = write_answers(tmp_path / "confirmed", "Two", answers[1:], "confirmed")
    derive(corpus, file, [unchecked, confirmed])
    assert Derivations.read(file).cases == {
        "o/one/wider": Derived(a_subsumes_b=Counterexample(counterexample=None))
    }


def test_the_file_is_written_as_it_is_read(tmp_path: Path) -> None:
    file = tmp_path / "derived.json"
    cases = {
        "o/one/b": Derived(a_subsumes_b=Counterexample(counterexample={"é": [None, 1.5]})),
        "o/one/a.2": Derived(b_subsumes_a=Agreement(checkers=["One 1.0", "Two 1.0"])),
        "o/one/a.10": Derived(a_subsumes_b=Counterexample(counterexample=None)),
    }
    Derivations.write(file, cases)
    assert Derivations.read(file).cases == cases
    lines = file.read_text(encoding="utf-8").splitlines()
    # One case on a line, sorted as the cases of the corpus are, and nothing that is not ASCII.
    assert [line.split('"')[1] for line in lines[3:6]] == ["o/one/a.10", "o/one/a.2", "o/one/b"]
    assert all(line.isascii() for line in lines)
    Derivations.write(file, {})
    assert Derivations.read(file).cases == {}


@pytest.mark.parametrize(
    "entry",
    [
        {"a_subsumes_b": {"checkers": ["One 1.0"]}},
        # Two versions of one checker are one checker.
        {"a_subsumes_b": {"checkers": ["One 1.0", "One 2.0"]}},
        {"a_subsumes_b": {"checkers": ["One 1.0", "Two 1.0"], "counterexample": 1}},
        {"a_subsumes_b": {}},
        {},
    ],
)
def test_a_file_that_is_not_what_the_model_says_is_not_read(tmp_path: Path, entry: Json) -> None:
    file = tmp_path / "derived.json"
    write_json(file, {"$schema": "./schemas/derived.schema.json", "cases": {"o/one/a": entry}})
    with pytest.raises(ConfigError):
        Derivations.read(file)


# --------------------------------------------------------------------------- the build


def test_the_build_gives_a_case_its_derived_labels_and_what_shows_them() -> None:
    cases = [open_case("o/one/a", TEXT, OPTIONAL), open_case("o/one/b", OPTIONAL, TEXT)]
    refuted = Derived(a_subsumes_b=Counterexample(counterexample=None))
    agreed = Derived(
        a_subsumes_b=Agreement(checkers=["One 1.0", "Two 1.0"]),
        b_subsumes_a=Counterexample(counterexample=None),
    )
    first, second = with_derived(cases, {"o/one/a": refuted, "o/one/b": agreed})
    assert (first.a_subsumes_b, first.b_subsumes_a) == (False, None)
    assert (second.a_subsumes_b, second.b_subsumes_a) == (True, False)
    written = second.document
    assert isinstance(written, dict)
    assert list(written)[-3:] == ["derived", "a", "b"]
    assert written["derived"] == {
        "a_subsumes_b": {"checkers": ["One 1.0", "Two 1.0"]},
        "b_subsumes_a": {"counterexample": None},
    }
    assert with_derived(cases, {}) == cases


def test_a_derived_label_stands_only_where_a_case_has_none() -> None:
    labelled = [open_case("o/one/a", TEXT, OPTIONAL, a_subsumes_b=False)]
    refuted = Derived(a_subsumes_b=Counterexample(counterexample=None))
    with pytest.raises(ConfigError, match="has a label"):
        with_derived(labelled, {"o/one/a": refuted})
    with pytest.raises(ConfigError, match="do not exist"):
        with_derived(labelled, {"o/one/b": refuted})
    overridden = [Case("o/one/a", TEXT, OPTIONAL, None, None, "x.json", note="Withdrawn.")]
    with pytest.raises(ConfigError, match=r"overrides\.json lists"):
        with_derived(overridden, {"o/one/a": refuted})


# --------------------------------------------------------------------------- the corpus


def test_a_question_without_a_label_is_asked_unless_another_case_asks_it() -> None:
    known = {case.id: case for case in cases()}
    asked = {(task.case, task.direction) for task in read_unlabelled(CORPUS)}
    assert asked
    forward = {(case.id, "a_subsumes_b") for case in cases() if case.a_subsumes_b is None}
    assert {question for question in asked if question[1] == "a_subsumes_b"} == forward
    questions = {
        (json.dumps(case.a, sort_keys=True), json.dumps(case.b, sort_keys=True)) for case in cases()
    }
    for case in cases():
        if case.b_subsumes_a is not None:
            assert (case.id, "b_subsumes_a") not in asked
            continue
        swapped = (json.dumps(case.b, sort_keys=True), json.dumps(case.a, sort_keys=True))
        assert ((case.id, "b_subsumes_a") in asked) == (swapped not in questions), case.id
    assert all(getattr(known[case], direction) is None for case, direction in asked)


def test_the_corpus_has_the_labels_of_the_file() -> None:
    derived = Derivations.read(ROOT / "derived.json").cases
    assert {case.id: case.derived for case in cases() if case.derived is not None} == {
        case: document(entry) for case, entry in derived.items()
    }
    known = {case.id: case for case in cases()}
    wrong = [
        f"{case} {direction}"
        for case, entry in derived.items()
        for direction, evidence in by_label(entry)
        if getattr(known[case], direction) is not label(evidence)
    ]
    assert wrong == []


def test_a_derived_counterexample_refutes_the_inclusion() -> None:
    checked = 0
    wrong = []
    for case, entry in Derivations.read(ROOT / "derived.json").cases.items():
        found = read_case(CORPUS / f"{case}.json")
        for direction, evidence in by_label(entry):
            if not isinstance(evidence, Counterexample):
                continue
            checked += 1
            accepting, narrower = (
                (found.a, found.b) if direction == "a_subsumes_b" else (found.b, found.a)
            )
            if not refutes(evidence.counterexample, accepting, narrower):
                wrong.append(f"{case} {direction}")
    assert wrong == []
    assert checked > 1000


def test_checkers_agree_only_where_they_read_the_schemas_as_the_corpus_does() -> None:
    known = {case.id: case for case in cases()}
    wrong = [
        case
        for case, entry in Derivations.read(ROOT / "derived.json").cases.items()
        if any(isinstance(evidence, Agreement) for _, evidence in by_label(entry))
        and READ_DIFFERENTLY & set(known[case].features)
    ]
    assert wrong == []


def test_the_schema_of_a_case_says_what_the_schema_of_the_file_says() -> None:
    of_case, of_file = (
        json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))["$defs"]
        for name in ("case.schema.json", "derived.schema.json")
    )
    assert of_file == {name: of_case[name] for name in of_file}
