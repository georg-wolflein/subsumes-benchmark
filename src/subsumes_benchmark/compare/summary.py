"""What a report says about the runs, as numbers: outcomes, solved shares and times."""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, assert_never

from subsumes_benchmark.compare.results import (
    RUN_FILE,
    Result,
    Run,
    read_results,
    read_run,
    seconds,
)
from subsumes_benchmark.compare.witness import refuted
from subsumes_benchmark.compare.words import count
from subsumes_benchmark.generated.comparison import (
    ComparedChecker,
    ComparedRun,
    ComparisonSpec,
    Outcomes,
)
from subsumes_benchmark.generated.result import (
    Crash,
    Error,
    No,
    Timeout,
    Unknown,
    Unsupported,
    Yes,
)

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


# How many points the curve of a run has at most: one for each thousandth of the tasks with a
# label, which is finer than a plot shows.
THOUSANDTHS = 1000


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

    def solved(self, keep: Callable[[Result], bool] | None = None) -> int:
        """How many tasks the checker solved: it gave the answer that the label gives."""
        return self.counts(keep)["correct"]

    def solved_seconds(self) -> Sequence[float]:
        """What the checker took on every task it solved, shortest first."""
        solved = (seconds(r) for r in self.results if outcome(r) == "correct")
        return sorted(taken for taken in solved if taken is not None)

    def seconds_to_solve(self) -> Sequence[float]:
        """The time within which the checker solved each thousandth of the labelled tasks.

        The first is the time within which it solved one thousandth of them, and the list
        ends with the last thousandth that it solved in full. A time is that of the slowest
        task among the fastest ones that make up the share, so tasks that were not solved
        count as slower than every task that was.
        """
        solved = self.solved_seconds()
        labelled = len(self.labelled())
        times = []
        for thousandths in range(1, THOUSANDTHS + 1):
            # The tasks that make up the share, rounded up, in whole numbers.
            needed = -(-thousandths * labelled // THOUSANDTHS)
            if not 0 < needed <= len(solved):
                break
            times.append(solved[needed - 1])
        return times

    def compared(self) -> ComparedRun:
        """As much of the run as a report shows."""
        checker = self.run.checker
        counts = self.counts()
        return ComparedRun(
            name=self.run.name,
            checker=ComparedChecker(
                label=checker.label,
                variant=checker.variant,
                version=checker.version,
                homepage=checker.homepage,
            ),
            outcomes=Outcomes(
                correct=counts["correct"],
                unlabelled=counts["unlabelled"],
                wrong_no=counts["wrong_no"],
                wrong_yes=counts["wrong_yes"],
                no_answer=counts["no_answer"],
                timeout=counts["timeout"],
            ),
            seconds_to_solve=list(self.seconds_to_solve()),
        )


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


class Comparison(ComparisonSpec):
    """The runs of a report, as much of them as it shows: the ``comparison.json`` of a report."""

    @classmethod
    def of(cls, entries: Sequence[Entry]) -> Self:
        """The comparison of some runs, which ``read_entries`` has checked are over the same."""
        first = entries[0]
        return cls(
            corpus=first.run.corpus,
            timeout=first.run.timeout,
            tasks=len(first.results),
            labelled_tasks=len(first.labelled()),
            runs=[entry.compared() for entry in entries],
        )

    def write(self, path: Path) -> None:
        # A key that does not apply is left out: a checker without a variant has none.
        path.write_text(f"{self.model_dump_json(indent=2, exclude_none=True)}\n", encoding="utf-8")

    def line(self) -> str:
        """A line for a person: the corpus, its tasks and the time for each."""
        return (
            f"Measured on corpus `{self.corpus}`: {count(self.tasks)} tasks, of which "
            f"{count(self.labelled_tasks)} have a label, with {self.timeout:g} seconds per task."
        )
