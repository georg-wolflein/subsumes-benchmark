"""The comparison of checkers: the tasks, what a report counts, and the folders under ``checkers/``."""

import json
import subprocess
import sys
from importlib.metadata import version
from typing import TYPE_CHECKING

import pytest

from reading import CORPUS, ROOT, case, cases
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.report import README_END, README_START, report, update_readme
from subsumes_benchmark.compare.results import (
    Answer,
    Result,
    Run,
    read_results,
    read_run,
    result_line,
    write_run,
)
from subsumes_benchmark.compare.run import prepare
from subsumes_benchmark.compare.summary import (
    Entry,
    ReportError,
    agreements,
    outcome,
    read_entries,
)
from subsumes_benchmark.compare.tasks import read_tasks, select
from subsumes_benchmark.compare.witness import Confirmation, Witness, confirm
from subsumes_benchmark.generated.case import CaseSpec

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from subsumes_benchmark import Json

CHECKERS = sorted(path.parent for path in (ROOT / "checkers").glob("*/checker.json"))


def a_run(checker: str = "one", label: str = "One", variant: str | None = None) -> Run:
    return Run(
        checker=checker,
        label=label,
        variant=variant,
        version="1.0",
        homepage="https://example.com",
        dialect="2020-12",
        corpus="v1.0.0",
        timeout=10.0,
        warmup=0,
        seed=0,
        tasks=0,
        platform="a machine",
        processor="a processor",
        started="2026-01-01T00:00:00+00:00",
        seconds=1.0,
    )


def a_result(
    case: str, answer: Answer, expected: bool | None = True, seconds: float | None = 0.001
) -> Result:
    return Result(case, "a_subsumes_b", expected, answer, seconds, seconds)


def write(folder: Path, run: Run, results: Sequence[Result]) -> None:
    folder.mkdir(parents=True)
    write_run(folder, run)
    (folder / "results.jsonl").write_text("".join(map(result_line, results)), encoding="utf-8")


def a_case(a: Json, b: Json, a_subsumes_b: bool | None = None) -> dict[str, Json]:
    """A case as its file has it, with nothing known about the other direction."""
    return {
        "$schema": "../case.schema.json",
        "a_subsumes_b": a_subsumes_b,
        "b_subsumes_a": None,
        "features": [],
        "upstream": "https://example.com",
        "a": a,
        "b": b,
    }


# --------------------------------------------------------------------------- the tasks


def test_a_case_is_asked_both_ways_with_the_label_of_each() -> None:
    tasks = read_tasks(CORPUS)
    forward = [task for task in tasks if task.direction == "a_subsumes_b"]
    backward = [task for task in tasks if task.direction == "b_subsumes_a"]
    assert [task.case for task in forward] == [case.id for case in cases()]
    assert [task.case for task in backward] == [case.id for case in cases()]
    assert [task.expected for task in forward] == [case.a_subsumes_b for case in cases()]
    assert [task.expected for task in backward] == [case.b_subsumes_a for case in cases()]
    # Asked the other way, the two schemas swap, so that the first is still the one that accepts.
    for task in (forward[0], backward[0]):
        found = case(task.case)
        first, second = prepare(task, "2020-12")
        expected = (found.a, found.b) if task.direction == "a_subsumes_b" else (found.b, found.a)
        assert (first, second) == expected


def test_a_sample_is_the_same_for_every_checker() -> None:
    tasks = read_tasks(CORPUS)
    assert select(tasks, limit=50) == select(tasks, limit=50)
    assert select(tasks, limit=50) == select(tasks)[:50]
    assert len({task.collection for task in select(tasks, limit=300)}) > 5


# --------------------------------------------------------------------------- the counterexamples


@pytest.mark.parametrize(
    ("a", "b", "instance", "confirmation"),
    [
        ({"type": "string"}, {"type": ["string", "null"]}, None, "confirmed"),
        ({"type": "string"}, {"type": ["string", "null"]}, 1, "not_an_instance"),
        ({"type": "string"}, {"type": ["string", "null"]}, "x", "accepted"),
        # `format` is asserted, and a pattern is one of ECMA-262, whose \d is an ASCII digit.
        ({"format": "ipv4"}, {"type": "string"}, "1.2.3", "confirmed"),
        ({"pattern": "^\\d$"}, {"maxLength": 1}, "\u0661", "confirmed"),
        # A pattern of ECMA-262 that the validator does not take.
        ({"pattern": "^[^\\0]+$"}, True, "x", "unchecked"),
        # A whole number that 64 bits do not hold is the double nearest to it, on both sides.
        ({"type": "string"}, {"const": 10**52 + 1}, 1e52, "confirmed"),
        ({"type": "string"}, {"const": 2**64 - 1}, 1.8446744073709552e19, "not_an_instance"),
        ({"type": "string"}, True, float("inf"), "unchecked"),
    ],
)
def test_a_validator_says_whether_a_counterexample_is_one(
    a: Json, b: Json, instance: Json, confirmation: Confirmation
) -> None:
    case = CaseSpec.model_validate(a_case(a, b))
    assert confirm(case, "a_subsumes_b", instance).confirmation == confirmation
    # Asked the other way, the two schemas swap.
    other = CaseSpec.model_validate(a_case(b, a))
    assert confirm(other, "b_subsumes_a", instance).confirmation == confirmation


def test_a_counterexample_that_was_not_checked_says_why() -> None:
    case = CaseSpec.model_validate(a_case({"pattern": "^[^\\0]+$"}, True))
    witness = confirm(case, "a_subsumes_b", "x")
    assert witness.instance == "x"
    assert witness.note is not None
    assert witness.note.startswith("the validator does not take a schema: ")
    assert not witness.refuted


# An adapter that says no with the `const` of B for a counterexample, where B has one, declines
# where A has a `format`, and says yes to everything else.
ADAPTER = """
import json, sys
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    a, b = request["a"], request["b"]
    if isinstance(b, dict) and "const" in b:
        reply = {"answer": "no", "counterexample": b["const"], "reason": "not kept"}
    elif isinstance(a, dict) and "format" in a:
        reply = {"answer": "unknown", "reason": "format", "detail": "format is not supported"}
    else:
        reply = {"answer": "yes", "counterexample": 1}
    print(json.dumps({"seconds": 0.001, **reply}), flush=True)
"""


def test_a_checker_and_a_corpus_from_anywhere_are_run_by_their_paths(tmp_path: Path) -> None:
    """The command as an installed package runs it: in a folder that is no checkout.

    The run keeps the kind of reason of an unknown, and asks about the counterexample of a no.
    """
    folder = tmp_path / "mine" / "fake"
    folder.mkdir(parents=True)
    (folder / "adapter.py").write_text(ADAPTER, encoding="utf-8")
    described: dict[str, Json] = {
        "$schema": "https://example.com/checker.schema.json",
        "label": "Fake",
        "version": "1",
        "homepage": "https://example.com",
        "dialect": "2020-12",
        "build": ["true"],
        "run": [sys.executable, "adapter.py"],
    }
    (folder / "checker.json").write_text(json.dumps(described), encoding="utf-8")
    corpus = tmp_path / "corpus"
    written = {
        "null": a_case({"type": "string"}, {"const": None}, a_subsumes_b=False),
        "none": a_case({"type": "null"}, {"const": None}, a_subsumes_b=True),
        "format": a_case({"format": "hostname"}, {"type": "string"}),
    }
    (corpus / "c").mkdir(parents=True)
    (corpus / "c" / "collection.json").write_text("{}", encoding="utf-8")
    for name, content in written.items():
        (corpus / "c" / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")

    # The paths are taken from the working directory, the corpus and the results by default.
    command = [sys.executable, "-m", "subsumes_benchmark.compare", "run", "mine/fake"]
    subprocess.run([*command, "--warmup", "0"], cwd=tmp_path, check=True, capture_output=True)

    out = tmp_path / "results" / "fake"
    # A corpus that is not the one of a checkout is taken to be that of the package's version.
    assert read_run(out).corpus == "v" + version("subsumes-benchmark")
    results = {(r.case, r.direction): r for r in read_results(out)}
    assert len(results) == 6
    # `null` is a counterexample like any other, and is told from none by the key.
    found = results["c/null", "a_subsumes_b"]
    assert (found.answer, found.witness, found.reason) == ("no", Witness(None, "confirmed"), None)
    assert outcome(found) == "correct"
    # A no with a counterexample that is none is wrong, whatever the label says.
    found = results["c/none", "a_subsumes_b"]
    assert found.witness == Witness(None, "accepted")
    assert outcome(found) == "wrong_no"
    # A reason belongs to an unknown and a counterexample to a no, and to nothing else.
    found = results["c/format", "a_subsumes_b"]
    assert (found.answer, found.reason, found.witness) == ("unknown", "format", None)
    found = results["c/format", "b_subsumes_a"]
    assert (found.answer, found.reason, found.witness) == ("yes", None, None)


# --------------------------------------------------------------------------- what a report counts


@pytest.mark.parametrize(
    ("answer", "expected", "counted"),
    [
        ("yes", True, "correct"),
        ("no", False, "correct"),
        ("yes", False, "wrong_yes"),
        ("no", True, "wrong_no"),
        ("yes", None, "unlabelled"),
        ("no", None, "unlabelled"),
        ("unknown", True, "no_answer"),
        ("unsupported", False, "no_answer"),
        ("error", None, "no_answer"),
        ("crash", True, "no_answer"),
        ("timeout", True, "timeout"),
    ],
)
def test_how_a_task_counts(answer: Answer, expected: bool | None, counted: str) -> None:
    assert outcome(a_result("c/1", answer, expected)) == counted


@pytest.mark.parametrize("expected", [True, False, None])
def test_a_no_counts_by_its_counterexample_before_its_label(expected: bool | None) -> None:
    def no(confirmation: Confirmation) -> Result:
        witness = Witness(1, confirmation)
        return Result("c/1", "a_subsumes_b", expected, "no", 0.001, 0.001, witness=witness)

    without = outcome(a_result("c/1", "no", expected))
    assert outcome(no("not_an_instance")) == "wrong_no"
    assert outcome(no("accepted")) == "wrong_no"
    assert outcome(no("confirmed")) == without
    assert outcome(no("unchecked")) == without


def test_only_a_task_with_a_label_is_solved_and_the_shares_are_of_those() -> None:
    entry = Entry(
        a_run(),
        [
            a_result("c/1", "yes", seconds=0.003),
            a_result("c/2", "no", expected=False, seconds=0.001),
            a_result("c/3", "no", seconds=0.0001),  # wrong, so not solved
            a_result("c/4", "unknown", seconds=0.0002),
            a_result("c/5", "no", expected=None, seconds=0.00001),  # answered, and no more
            a_result("d/1", "yes", expected=None),
        ],
    )
    assert [result.case for result in entry.labelled()] == ["c/1", "c/2", "c/3", "c/4"]
    assert [result.case for result in entry.unlabelled()] == ["c/5", "d/1"]
    assert entry.solved() == 2
    assert entry.solved_seconds() == [0.001, 0.003]
    # Of the four tasks with a label; those that were not solved count as slower.
    assert entry.seconds_to_solve(0.25) == 0.001
    assert entry.seconds_to_solve(0.5) == 0.003
    assert entry.seconds_to_solve(0.75) is None
    assert entry.collections() == {"c": (2, 4), "d": (0, 0)}
    assert entry.solved(lambda result: result.case == "c/1") == 1


def test_variants_of_a_checker_are_compared_answer_by_answer() -> None:
    first = Entry(
        a_run("one", variant="Rust"),
        [a_result("c/1", "yes"), a_result("c/2", "no"), a_result("c/3", "unknown")],
    )
    second = Entry(
        a_run("one-python", variant="Python"),
        [a_result("c/1", "yes"), a_result("c/2", "timeout"), a_result("c/3", "no")],
    )
    other = Entry(a_run("two", label="Two"), first.results)
    (found,) = agreements([first, second, other])
    assert (found.first, found.second) == ("One (Rust)", "One (Python)")
    assert (found.tasks, found.same, found.unstable) == (3, 1, 1)


def test_runs_are_listed_by_label_and_must_be_over_the_same_tasks(tmp_path: Path) -> None:
    results = [a_result("c/1", "yes")]
    write(tmp_path / "b", a_run("zeta", label="alpha", variant="Python"), results)
    write(tmp_path / "a", a_run("beta", label="Beta"), results)
    write(tmp_path / "c", a_run("alpha", label="alpha", variant="Rust"), results)
    (tmp_path / "not-a-run").mkdir()
    assert [entry.name for entry in read_entries(tmp_path)] == [
        "alpha (Rust)",
        "alpha (Python)",
        "Beta",
    ]
    write(tmp_path / "d", a_run("gamma", label="Gamma"), [a_result("c/2", "yes")])
    with pytest.raises(ReportError, match="did not run the tasks"):
        read_entries(tmp_path)


def test_a_report_is_written_and_shown_in_the_readme(tmp_path: Path) -> None:
    labelled = [case for case in cases() if case.a_subsumes_b is not None]
    case = next(case for case in labelled if "format" not in case.features)
    with_format = next(case for case in labelled if "format" in case.features)
    without_label = next(case for case in cases() if case.b_subsumes_a is None)
    results = [
        a_result(case.id, "yes", case.a_subsumes_b, 0.002),
        a_result(with_format.id, "no", with_format.a_subsumes_b, 0.5),
        Result(
            without_label.id,
            "b_subsumes_a",
            None,
            "no",
            0.001,
            0.001,
            witness=Witness(1, "accepted"),
        ),
    ]
    write(tmp_path / "results" / "one", a_run("one", variant="Rust"), results)
    write(tmp_path / "results" / "two", a_run("two", variant="Python"), results[::-1])
    readme = tmp_path / "README.md"
    readme.write_text(f"before\n{README_START}\nold\n{README_END}\nafter\n", encoding="utf-8")

    report(tmp_path / "results", tmp_path / "comparison", CORPUS, readme)

    text = (tmp_path / "comparison" / "report.md").read_text(encoding="utf-8")
    assert "a sample of 3 of the" in text
    assert "of which 2 have a label" in text
    assert "The 1 tasks without a label." in text
    assert "The 1 whose schemas use `format`" in text
    # Said no, with a counterexample, and what the validator made of it.
    assert "| One (Rust) | 2 | 1 | 0 | 0 | 1 | 0 |" in text
    assert "One (Rust) and One (Python) gave the same answer on 3 of 3 tasks." in text
    for name in ("chart-light.svg", "chart-dark.svg"):
        assert (tmp_path / "comparison" / name).read_text(encoding="utf-8").startswith("<?xml")
    shown = readme.read_text(encoding="utf-8")
    assert shown.startswith(f"before\n{README_START}\n\n<picture>")
    assert shown.endswith(f"{README_END}\nafter\n")
    assert 'src="comparison/chart-light.svg"' in shown
    assert "old" not in shown


def test_a_readme_without_the_markers_is_left_alone(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("nothing to replace\n", encoding="utf-8")
    with pytest.raises(ValueError, match="markers"):
        update_readme(readme, "a block")
    assert readme.read_text(encoding="utf-8") == "nothing to replace\n"


def test_the_readme_has_the_place_for_the_report() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.count(README_START) == 1
    assert text.count(README_END) == 1


# --------------------------------------------------------------------------- the folders


# The file of each folder that pins the checker's version, and how the version stands in it.
PINS = {
    "confluent": ("pom.xml", "<confluent.version>{}</confluent.version>"),
    "jsoncompat": ("Cargo.toml", 'jsoncompat = "={}"'),
    "jsoncompat-python": ("adapter.py", "jsoncompat=={}"),
    "jsonsubschema": ("adapter.py", "jsonsubschema=={}"),
    # RWG is compiled from the submodule, whose commit the corpus records for every
    # collection that is built from it.
    "rwg": ("../../corpus/rb-testset/collection.json", '"commit": "{}'),
    "subsumes": ("Cargo.toml", 'subsumes = "={}"'),
    "subsumes-python": ("adapter.py", "subsumes=={}"),
}


def test_every_checker_is_in_the_workflow_and_the_documentation() -> None:
    names = [folder.name for folder in CHECKERS]
    assert names == sorted(PINS)
    workflow = (ROOT / ".github" / "workflows" / "comparison.yml").read_text(encoding="utf-8")
    assert f"checker: [{', '.join(names)}]" in workflow
    documentation = (ROOT / "checkers" / "README.md").read_text(encoding="utf-8")
    assert all(f"| `{name}/` |" in documentation for name in names)


@pytest.mark.parametrize("folder", CHECKERS, ids=lambda folder: folder.name)
def test_a_checker_states_the_version_its_folder_pins(folder: Path) -> None:
    checker = Checker.load(folder)
    file, form = PINS[folder.name]
    assert form.format(checker.version) in (folder / file).read_text(encoding="utf-8")


def test_variants_of_a_checker_pin_the_same_version() -> None:
    versions: dict[str, set[str]] = {}
    for folder in CHECKERS:
        checker = Checker.load(folder)
        versions.setdefault(checker.label, set()).add(checker.version)
    assert {label for label, found in versions.items() if len(found) > 1} == set()
