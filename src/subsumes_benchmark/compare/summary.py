"""What a report says about the runs, as numbers: outcomes, solved shares and times."""

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never, get_args

from subsumes_benchmark.compare.results import (
    RUN_FILE,
    Result,
    Run,
    collection,
    ending,
    read_results,
    read_run,
    seconds,
)
from subsumes_benchmark.compare.tasks import case_files
from subsumes_benchmark.compare.witness import refuted
from subsumes_benchmark.generated.case import CaseSpec
from subsumes_benchmark.generated.result import (
    Crash,
    Error,
    No,
    Timeout,
    Unknown,
    Unsupported,
    Yes,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from subsumes_benchmark.generated.result import Direction

type Outcome = Literal["correct", "unlabelled", "wrong_no", "wrong_yes", "no_answer", "timeout"]
"""How a task counts.

- ``correct``: the checker answered what the corpus says. The task is solved.
- ``unlabelled``: the checker answered and the corpus claims nothing, so the answer can be
  held against nothing.
- ``wrong_no``: the checker said no where A subsumes B, or gave a counterexample with its no
  that is none. The second needs no label.
- ``wrong_yes``: the checker said yes where A does not subsume B.
- ``no_answer``: the checker declined, failed, or cannot read the schemas.
- ``timeout``: the checker did not answer in time.
"""

OUTCOMES: Sequence[Outcome] = get_args(Outcome.__value__)
# How a task with a label can count, and how one without.
LABELLED: Sequence[Outcome] = ("correct", "wrong_no", "wrong_yes", "no_answer", "timeout")
UNLABELLED: Sequence[Outcome] = ("unlabelled", "wrong_no", "no_answer", "timeout")
OUTCOME_NAMES: Mapping[Outcome, str] = {
    "correct": "Correct",
    "unlabelled": "Answered",
    "wrong_no": "Wrong no",
    "wrong_yes": "Wrong yes",
    "no_answer": "No answer",
    "timeout": "Timed out",
}


class ReportError(Exception):
    pass


def has_label(result: Result) -> bool:
    """Whether the corpus says what the answer is."""
    return result.expected is not None


def outcome(result: Result) -> Outcome:
    match result:
        case No() if result.witness is not None and refuted(result.witness):
            return "wrong_no"
        case Yes() | No():
            if result.expected is None:
                return "unlabelled"
            if result.answer == result.expected:
                return "correct"
            return "wrong_yes" if result.answer else "wrong_no"
        case Timeout():
            return "timeout"
        case Unknown() | Unsupported() | Error() | Crash():
            return "no_answer"
        case _:
            assert_never(result)


@dataclass(frozen=True)
class Agreement:
    """How far two variants of one checker gave the same answers."""

    first: str
    second: str
    tasks: int
    same: int
    # Differences in which one side ran out of time or its process died, which the load of
    # the machine can cause.
    unstable: int


@dataclass(frozen=True)
class Entry:
    """One checker's run and its result on every task."""

    run: Run
    results: Sequence[Result]

    @property
    def name(self) -> str:
        return self.run.title

    def counts(self, keep: Callable[[Result], bool] | None = None) -> Counter[Outcome]:
        """How many tasks ended each way, among those that ``keep`` lets through."""
        return Counter(outcome(r) for r in self.results if keep is None or keep(r))

    def labelled(self, keep: Callable[[Result], bool] | None = None) -> Sequence[Result]:
        """The tasks that the corpus has a label for, among those that ``keep`` lets through."""
        return [r for r in self.results if has_label(r) and (keep is None or keep(r))]

    def unlabelled(self) -> Sequence[Result]:
        return [r for r in self.results if not has_label(r)]

    def solved(self, keep: Callable[[Result], bool] | None = None) -> int:
        """How many tasks the checker solved: it gave the answer that the label gives."""
        return self.counts(keep)["correct"]

    def solved_seconds(self) -> Sequence[float]:
        """What the checker took on every task it solved, shortest first."""
        solved = (seconds(r) for r in self.results if outcome(r) == "correct")
        return sorted(taken for taken in solved if taken is not None)

    def seconds_to_solve(self, share: float) -> float | None:
        """The time within which the checker solved this share of the labelled tasks, if it did.

        This is the time of the slowest task among the fastest ones that make up the share,
        so tasks that were not solved count as slower than every task that was.
        """
        solved = self.solved_seconds()
        needed = math.ceil(share * len(self.labelled()))
        return solved[needed - 1] if 0 < needed <= len(solved) else None

    def collections(self) -> Mapping[str, tuple[int, int]]:
        """The solved tasks and the labelled tasks of every collection."""
        tasks = Counter(collection(r) for r in self.labelled())
        solved = Counter(collection(r) for r in self.results if outcome(r) == "correct")
        names = sorted({collection(r) for r in self.results})
        return {name: (solved[name], tasks[name]) for name in names}


def read_entry(folder: Path) -> Entry:
    """The run that a folder holds, as ``run`` wrote it.

    Raises:
        ReportError: The folder holds no run.
    """
    if not (folder / RUN_FILE).is_file():
        raise ReportError(f"no run in {folder}")
    return Entry(read_run(folder), read_results(folder))


def read_entries(folder: Path) -> Sequence[Entry]:
    """The runs under a folder, one per subfolder, in the order a report lists them.

    The order is that of the labels and then of the folders under ``checkers/``, whatever the
    results are, so that a checker keeps its place and its colour from one report to the next.

    Raises:
        ReportError: There is no run, or the runs are not over the same tasks.
    """
    entries = [read_entry(path) for path in sorted(folder.iterdir()) if (path / RUN_FILE).is_file()]
    if not entries:
        raise ReportError(f"no run under {folder}")
    entries.sort(key=lambda e: (e.run.checker.label.casefold(), e.run.name))
    tasks = {(r.case, r.direction) for r in entries[0].results}
    for entry in entries:
        if {(r.case, r.direction) for r in entry.results} != tasks:
            raise ReportError(f"{entry.name} did not run the tasks that {entries[0].name} ran")
        if (entry.run.corpus, entry.run.timeout) != (entries[0].run.corpus, entries[0].run.timeout):
            raise ReportError(f"{entry.name} ran on another corpus or with another timeout")
    return entries


def agreements(entries: Sequence[Entry]) -> Sequence[Agreement]:
    """Every pair of variants of one checker, compared answer by answer."""
    found = []
    for i, first in enumerate(entries):
        for second in entries[i + 1 :]:
            if first.run.checker.label != second.run.checker.label:
                continue
            answers = {(r.case, r.direction): ending(r) for r in second.results}
            pairs = [(ending(r), answers[r.case, r.direction]) for r in first.results]
            different = [pair for pair in pairs if pair[0] != pair[1]]
            found.append(
                Agreement(
                    first=first.name,
                    second=second.name,
                    tasks=len(pairs),
                    same=len(pairs) - len(different),
                    unstable=sum(1 for pair in different if {"timeout", "crash"} & set(pair)),
                )
            )
    return found


def cases_using(corpus: Path, feature: str) -> frozenset[str]:
    """The ids of the cases that list the feature."""
    return frozenset(
        case for case, path in case_files(corpus).items() if feature in CaseSpec.read(path).features
    )


def derived_tasks(corpus: Path) -> frozenset[tuple[str, Direction]]:
    """The tasks whose label is derived, where upstream gives none: each a case and a direction."""
    found: set[tuple[str, Direction]] = set()
    for case, path in case_files(corpus).items():
        derived = CaseSpec.read(path).derived
        if derived is None:
            continue
        if derived.a_subsumes_b is not None:
            found.add((case, "a_subsumes_b"))
        if derived.b_subsumes_a is not None:
            found.add((case, "b_subsumes_a"))
    return frozenset(found)
