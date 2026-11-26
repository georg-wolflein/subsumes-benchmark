"""The comparison of checkers: the tasks, what a report counts, and the folders under ``checkers/``."""

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

import runs
from reading import CORPUS, ROOT, case, cases
from runs import Confirmation, a_run, a_witness, write
from subsumes_benchmark import Json
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.report import block, report
from subsumes_benchmark.compare.results import Ending, Result, ending, read_results, read_run
from subsumes_benchmark.compare.run import prepare
from subsumes_benchmark.compare.summary import (
    Comparison,
    Entry,
    ReportError,
    outcome,
    read_entries,
)
from subsumes_benchmark.compare.tasks import read_tasks, select
from subsumes_benchmark.compare.witness import confirm, refuted
from subsumes_benchmark.generated.case import CaseSpec
from subsumes_benchmark.generated.result import Checked, Crash, No, Unchecked, Unknown, Yes

CHECKERS = sorted(path.parent for path in (ROOT / "checkers").glob("*/checker.json"))


def a_result(
    case: str, ended: Ending, expected: bool | None = True, seconds: float = 0.001
) -> Result:
    return runs.a_result(case, ended, expected, seconds=seconds)


def a_case(a: Json, b: Json, a_subsumes_b: bool | None = None) -> dict[str, Json]:
    """A case as its file has it, with nothing known about the other direction."""
    return {
        "$schema": "../../case.schema.json",
        "labels": {
            "a_subsumes_b": None
            if a_subsumes_b is None
            else {"kind": "source", "answer": a_subsumes_b},
            "b_subsumes_a": None,
        },
        "built_from": {"kind": "source", "link": "https://example.com"},
        "features": [],
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
    assert isinstance(witness, Unchecked)
    assert witness.counterexample == "x"
    assert witness.message.startswith("the validator does not take a schema: ")
    assert not refuted(witness)
    # A number that is none in JSON is not kept, since a file of results could not hold it.
    dropped = confirm(case, "a_subsumes_b", float("nan"))
    assert isinstance(dropped, Unchecked)
    assert "counterexample" not in dropped.model_fields_set


# An adapter that says no with the `const` of B for a counterexample, where B has one, declines
# where A has a `format`, and says yes to everything else. Where A has a `title`, it gives a
# line that is no reply: a yes with a key that only a no has.
ADAPTER = """
import json, sys
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    assert set(request) == {"a", "b", "timeout"}
    a, b = request["a"], request["b"]
    if isinstance(a, dict) and "title" in a:
        reply = {"answer": True, "seconds": 0.001, "counterexample": 1}
    elif isinstance(b, dict) and "const" in b:
        reply = {"answer": False, "seconds": 0.001, "counterexample": b["const"]}
    elif isinstance(a, dict) and "format" in a:
        reply = {"answer": None, "seconds": 0.001, "reason": "format", "message": "no format"}
    else:
        reply = {"answer": True, "seconds": 0}
    print(json.dumps(reply), flush=True)
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
        "typo": a_case({"title": "a reply that is none"}, True),
    }
    (corpus / "o" / "c").mkdir(parents=True)
    for name, content in written.items():
        (corpus / "o" / "c" / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")

    # The paths are taken from the working directory, the corpus and the results by default.
    command = [sys.executable, "-m", "subsumes_benchmark.compare", "run", "mine/fake"]
    subprocess.run([*command, "--warmup", "0"], cwd=tmp_path, check=True, capture_output=True)

    out = tmp_path / "results" / "fake"
    # A corpus that is not the one of a checkout is taken to be that of the package's version.
    assert read_run(out).corpus == "v" + version("subsumes-benchmark")
    results = {(r.case, r.direction): r for r in read_results(out)}
    assert len(results) == 8
    # `null` is a counterexample like any other, and is told from none by the key.
    found = results["o/c/null", "a_subsumes_b"]
    assert isinstance(found, No)
    assert found.witness == Checked(counterexample=None, confirmation="confirmed")
    assert outcome(found) == "correct"
    # A no with a counterexample that is none is wrong, whatever the label says.
    found = results["o/c/none", "a_subsumes_b"]
    assert isinstance(found, No)
    assert found.witness == Checked(counterexample=None, confirmation="accepted")
    assert outcome(found) == "wrong_no"
    found = results["o/c/format", "a_subsumes_b"]
    assert isinstance(found, Unknown)
    assert (found.reason, found.message) == ("format", "no format")
    # A whole number of seconds is a number of seconds.
    found = results["o/c/format", "b_subsumes_a"]
    assert isinstance(found, Yes)
    assert found.seconds == 0.0
    # A counterexample belongs to a no. A line with a key that its answer does not have is no
    # reply: the task counts as a crash, and the adapter is started again for the next.
    found = results["o/c/typo", "a_subsumes_b"]
    assert isinstance(found, Crash)
    assert found.message.startswith("not a reply (counterexample: Extra inputs are not permitted)")
    assert ending(results["o/c/typo", "b_subsumes_a"]) == "yes"
    # A key that does not apply is left out of a line, and is not written as null.
    lines = (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
    written = {(line["case"], line["direction"]): line for line in map(json.loads, lines)}
    assert written["o/c/format", "b_subsumes_a"] == {
        "case": "o/c/format",
        "direction": "b_subsumes_a",
        "expected": None,
        "answer": True,
        "seconds": 0.0,
        "wall_seconds": written["o/c/format", "b_subsumes_a"]["wall_seconds"],
    }
    assert set(written["o/c/typo", "a_subsumes_b"]) == {
        "case",
        "direction",
        "expected",
        "failure",
        "message",
        "wall_seconds",
    }
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert (run["name"], run["jobs"], run["checker"]) == ("fake", 1, described)


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
def test_how_a_task_counts(answer: Ending, expected: bool | None, counted: str) -> None:
    assert outcome(a_result("o/c/1", answer, expected)) == counted


@pytest.mark.parametrize("expected", [True, False, None])
def test_a_no_counts_by_its_counterexample_before_its_label(expected: bool | None) -> None:
    def no(confirmation: Confirmation) -> Result:
        return runs.a_result("o/c/1", "no", expected, witness=a_witness(confirmation))

    without = outcome(a_result("o/c/1", "no", expected))
    assert outcome(no("not_an_instance")) == "wrong_no"
    assert outcome(no("accepted")) == "wrong_no"
    assert outcome(no("confirmed")) == without
    assert outcome(no("unchecked")) == without


def test_only_a_task_with_a_label_is_solved_and_the_shares_are_of_those() -> None:
    entry = Entry(
        a_run(),
        [
            a_result("o/c/1", "yes", seconds=0.003),
            a_result("o/c/2", "no", expected=False, seconds=0.001),
            a_result("o/c/3", "no", seconds=0.0001),  # wrong, so not solved
            a_result("o/c/4", "unknown", seconds=0.0002),
            a_result("o/c/5", "no", expected=None, seconds=0.00001),  # answered, and no more
            a_result("o/d/1", "yes", expected=None),
        ],
    )
    assert [result.case for result in entry.labelled()] == ["o/c/1", "o/c/2", "o/c/3", "o/c/4"]
    assert entry.solved() == 2
    assert entry.solved_seconds() == [0.001, 0.003]
    # The time for each thousandth of the four tasks with a label: a quarter of them is one
    # task and half of them two, and no more were solved, so the list ends there. Those that
    # were not solved count as slower.
    times = entry.seconds_to_solve()
    assert len(times) == 500
    assert set(times[:250]) == {0.001}
    assert set(times[250:]) == {0.003}
    compared = entry.compared()
    assert compared.seconds_to_solve == times
    assert compared.outcomes.model_dump() == {
        "correct": 2, "unlabelled": 2, "wrong_no": 1, "wrong_yes": 0, "no_answer": 1,
        "timeout": 0,
    }  # fmt: skip
    assert entry.solved(lambda result: result.case == "o/c/1") == 1


def test_runs_are_listed_by_label_and_must_be_over_the_same_tasks(tmp_path: Path) -> None:
    results = [a_result("o/c/1", "yes")]
    write(tmp_path / "b", a_run("zeta", label="alpha", variant="Python"), results)
    write(tmp_path / "a", a_run("beta", label="Beta"), results)
    write(tmp_path / "c", a_run("alpha", label="alpha", variant="Rust"), results)
    (tmp_path / "not-a-run").mkdir()
    assert [entry.name for entry in read_entries(tmp_path)] == [
        "alpha (Rust)",
        "alpha (Python)",
        "Beta",
    ]
    write(tmp_path / "d", a_run("gamma", label="Gamma"), [a_result("o/c/2", "yes")])
    with pytest.raises(ReportError, match="did not run the tasks"):
        read_entries(tmp_path)


def test_a_report_draws_the_plots_and_gives_the_table(tmp_path: Path) -> None:
    holds = next(case for case in cases() if case.a_subsumes_b is True)
    fails = next(case for case in cases() if case.a_subsumes_b is False)
    declined = next(case for case in cases() if case.b_subsumes_a is True)
    without_label = next(case for case in cases() if case.b_subsumes_a is None)
    results = [
        a_result(holds.id, "yes", True, 0.002),
        a_result(fails.id, "no", False, 0.5),
        runs.a_result(
            without_label.id, "no", None, direction="b_subsumes_a", witness=a_witness("accepted")
        ),
        runs.a_result(declined.id, "unknown", True, direction="b_subsumes_a", seconds=0.01),
    ]
    # The second checker is slower on the task that decides the time of the fastest half, and
    # the third solves one task only.
    slower = [results[0], a_result(fails.id, "no", False, 0.7), *results[2:]]
    worse = [runs.a_result(holds.id, "unknown", True, seconds=0.01), *results[1:]]
    write(tmp_path / "results" / "one", a_run("one", variant="Rust"), results)
    write(tmp_path / "results" / "two", a_run("two", variant="Python"), slower[::-1])
    write(tmp_path / "results" / "worse", a_run("worse", label="Another"), worse)

    text = report(tmp_path / "results", tmp_path / "comparison")

    # A row for every run, named by a link to where the checker lives. The run that solved
    # most is first, though its checker is not the first by name, and runs that solved
    # equally many keep their order.
    table, scope = text.split("\n\n")
    rows = [line.strip("| ").split(" | ") for line in table.splitlines()]
    assert rows[0] == ["Checker", "Version", "Correct results", "Incorrect results",
                       "Fastest 50% within", "Fastest 90% within"]  # fmt: skip
    assert [row[0] for row in rows[2:]] == [
        "[One (Rust)](https://example.com)",
        "[One (Python)](https://example.com)",
        "[Another](https://example.com)",
    ]
    # Two of the three tasks with a label are solved. The no with a counterexample that is
    # none is wrong, though its task has no label. The best of a column is bold wherever it
    # stands, a column where every checker has the same has all of it bold, and one where
    # none has a value has nothing bold.
    assert [row[2:] for row in rows[2:]] == [
        ["**66.7%**", "**33.3%**", "**500 ms**", "—"],
        ["**66.7%**", "**33.3%**", "700 ms", "—"],
        ["33.3%", "**33.3%**", "—", "—"],
    ]
    assert scope.startswith("Measured on corpus `v1.0.0`: 4 tasks, of which 3 have a label, with")
    assert sorted(path.name for path in (tmp_path / "comparison").iterdir()) == [
        "chart-dark.svg",
        "chart-light.svg",
        "comparison.json",
        "results.md",
    ]
    for name in ("chart-light.svg", "chart-dark.svg"):
        chart = (tmp_path / "comparison" / name).read_text(encoding="utf-8")
        assert chart.startswith("<?xml")
        # One curve per checker, and the name of the one that solved most is bold.
        assert chart.count("font-weight: 700") == 1
    assert (tmp_path / "comparison" / "results.md").read_text(encoding="utf-8") == f"{table}\n"
    # The comparison says what the runs are over, and of each run as much as the report
    # shows. A checker without a variant has no such key.
    file = tmp_path / "comparison" / "comparison.json"
    comparison = json.loads(file.read_text(encoding="utf-8"))
    assert {key: value for key, value in comparison.items() if key != "runs"} == {
        "corpus": "v1.0.0",
        "timeout": a_run("one").timeout,
        "tasks": 4,
        "labelled_tasks": 3,
    }
    assert [run["name"] for run in comparison["runs"]] == ["worse", "one", "two"]
    assert comparison["runs"][0]["checker"] == {
        "label": "Another", "version": "1.0", "homepage": "https://example.com",
    }  # fmt: skip
    assert comparison["runs"][1]["checker"]["variant"] == "Rust"
    assert comparison["runs"][1]["outcomes"] == {
        "correct": 2, "unlabelled": 0, "wrong_no": 1, "wrong_yes": 0, "no_answer": 1,
        "timeout": 0,
    }  # fmt: skip

    # The plots and the table are made from the comparison alone: given the file in place of
    # the runs, the report writes the same ones again.
    again = tmp_path / "again"
    assert report(file, again) == text
    assert sorted(path.name for path in again.iterdir()) == [
        "chart-dark.svg",
        "chart-light.svg",
        "results.md",
    ]
    for path in again.iterdir():
        assert path.read_bytes() == (tmp_path / "comparison" / path.name).read_bytes(), path.name


def test_the_committed_table_is_what_the_committed_comparison_gives() -> None:
    comparison = Comparison.read(ROOT / "comparison" / "comparison.json")
    table = (ROOT / "comparison" / "results.md").read_text(encoding="utf-8")
    assert table == f"{block(comparison)}\n", "`make readme` writes the table again"


# --------------------------------------------------------------------------- the folders


# The file of each folder that pins the checker's version, and how the version stands in it.
PINS = {
    "confluent": ("pom.xml", "<confluent.version>{}</confluent.version>"),
    "jsoncompat": ("Cargo.toml", 'jsoncompat = "={}"'),
    "jsoncompat-python": ("adapter.py", "jsoncompat=={}"),
    "jsonsubschema": ("adapter.py", "jsonsubschema=={}"),
    # RWG is compiled from the submodule, whose commit the corpus records for every
    # collection that is built from it.
    "rwg": ("../../corpus/collections.json", '"commit": "{}'),
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
