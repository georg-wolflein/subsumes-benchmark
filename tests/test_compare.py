"""The comparison of checkers: the tasks, what a report counts, and the folders under ``checkers/``."""

from typing import TYPE_CHECKING

import pytest

from reading import CORPUS, ROOT, cases
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.report import README_END, README_START, report, update_readme
from subsumes_benchmark.compare.results import Answer, Result, Run, result_line, write_run
from subsumes_benchmark.compare.summary import (
    Entry,
    ReportError,
    agreements,
    outcome,
    read_entries,
)
from subsumes_benchmark.compare.tasks import read_tasks, select

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

CHECKERS = sorted(path.parent for path in (ROOT / "checkers").glob("*/checker.toml"))


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


# --------------------------------------------------------------------------- the tasks


def test_a_case_is_asked_the_other_way_only_where_it_has_a_label_for_it() -> None:
    tasks = read_tasks(CORPUS)
    forward = [task for task in tasks if task.direction == "a_subsumes_b"]
    backward = [task for task in tasks if task.direction == "b_subsumes_a"]
    assert [task.case for task in forward] == [case.id for case in cases()]
    assert {task.case for task in backward} == {
        case.id for case in cases() if case.b_subsumes_a is not None
    }
    # Asked the other way, the two schemas swap, so that A is still the one that accepts.
    assert all(task.a.name == "b.json" and task.b.name == "a.json" for task in backward)


def test_a_sample_is_the_same_for_every_checker() -> None:
    tasks = read_tasks(CORPUS)
    assert select(tasks, limit=50) == select(tasks, limit=50)
    assert select(tasks, limit=50) == select(tasks)[:50]
    assert len({task.collection for task in select(tasks, limit=300)}) > 5


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


def test_the_time_to_solve_a_share_counts_unsolved_tasks_as_slower() -> None:
    entry = Entry(
        a_run(),
        [
            a_result("c/1", "yes", seconds=0.003),
            a_result("c/2", "no", expected=None, seconds=0.001),
            a_result("c/3", "no", seconds=0.0001),  # wrong, so not solved
            a_result("c/4", "unknown", seconds=0.0002),
        ],
    )
    assert entry.solved() == 2
    assert entry.solved_seconds() == [0.001, 0.003]
    assert entry.seconds_to_solve(0.25) == 0.001
    assert entry.seconds_to_solve(0.5) == 0.003
    assert entry.seconds_to_solve(0.75) is None
    assert entry.collections() == {"c": (2, 4)}
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
    case = cases()[0]
    with_format = next(case for case in cases() if "format" in case.features)
    results = [
        a_result(case.id, "yes", case.a_subsumes_b, 0.002),
        a_result(with_format.id, "no", with_format.a_subsumes_b, 0.5),
    ]
    write(tmp_path / "results" / "one", a_run("one", variant="Rust"), results)
    write(tmp_path / "results" / "two", a_run("two", variant="Python"), results[::-1])
    readme = tmp_path / "README.md"
    readme.write_text(f"before\n{README_START}\nold\n{README_END}\nafter\n", encoding="utf-8")

    report(tmp_path / "results", tmp_path / "comparison", CORPUS, readme)

    text = (tmp_path / "comparison" / "report.md").read_text(encoding="utf-8")
    assert "a sample of 2 of the" in text
    assert "The 1 tasks whose schemas use `format`" in text
    assert "One (Rust) and One (Python) gave the same answer on 2 of 2 tasks." in text
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
