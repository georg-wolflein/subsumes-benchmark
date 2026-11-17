"""What a report says about the runs, as numbers: outcomes, solved shares and times."""

import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never, get_args

from subsumes_benchmark.compare.results import RUN_FILE, Result, Run, read_results, read_run

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

type Outcome = Literal["correct", "unlabelled", "wrong_no", "wrong_yes", "no_answer", "timeout"]
"""How a task counts.

- ``correct``: the checker answered what the corpus says.
- ``unlabelled``: the checker answered and the corpus claims nothing.
- ``wrong_no``: the checker said no where A subsumes B.
- ``wrong_yes``: the checker said yes where A does not subsume B.
- ``no_answer``: the checker declined, failed, or cannot read the schemas.
- ``timeout``: the checker did not answer in time.
"""

OUTCOMES: Sequence[Outcome] = get_args(Outcome.__value__)
OUTCOME_NAMES: Mapping[Outcome, str] = {
    "correct": "Correct",
    "unlabelled": "Answered, no label",
    "wrong_no": "Wrong no",
    "wrong_yes": "Wrong yes",
    "no_answer": "No answer",
    "timeout": "Timed out",
}
# A task is solved when the checker answered and no label contradicts the answer.
SOLVED: frozenset[Outcome] = frozenset({"correct", "unlabelled"})


class ReportError(Exception):
    pass


def outcome(result: Result) -> Outcome:
    match result.answer:
        case "yes" | "no":
            if result.expected is None:
                return "unlabelled"
            if result.expected == (result.answer == "yes"):
                return "correct"
            return "wrong_yes" if result.answer == "yes" else "wrong_no"
        case "timeout":
            return "timeout"
        case "unknown" | "unsupported" | "error" | "crash":
            return "no_answer"
        case _:
            assert_never(result.answer)


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
        return self.run.name

    def counts(self, keep: Callable[[Result], bool] | None = None) -> Counter[Outcome]:
        """How many tasks ended each way, among those that ``keep`` lets through."""
        return Counter(outcome(r) for r in self.results if keep is None or keep(r))

    def solved(self, keep: Callable[[Result], bool] | None = None) -> int:
        counts = self.counts(keep)
        return sum(counts[o] for o in SOLVED)

    def solved_seconds(self) -> Sequence[float]:
        """What the checker took on every task it solved, shortest first."""
        return sorted(
            r.seconds for r in self.results if outcome(r) in SOLVED and r.seconds is not None
        )

    def seconds_to_solve(self, share: float) -> float | None:
        """The time within which the checker solved this share of all tasks, if it did.

        This is the time of the slowest task among the fastest ones that make up the share,
        so tasks that were not solved count as slower than every task that was.
        """
        seconds = self.solved_seconds()
        needed = math.ceil(share * len(self.results))
        return seconds[needed - 1] if 0 < needed <= len(seconds) else None

    def collections(self) -> Mapping[str, tuple[int, int]]:
        """The solved tasks and all tasks of every collection."""
        tasks = Counter(r.collection for r in self.results)
        solved = Counter(r.collection for r in self.results if outcome(r) in SOLVED)
        return {name: (solved[name], tasks[name]) for name in sorted(tasks)}


def read_entries(folder: Path) -> Sequence[Entry]:
    """The runs under a folder, one per subfolder, in the order a report lists them.

    The order is that of the labels and then of the folders under ``checkers/``, whatever the
    results are, so that a checker keeps its place and its colour from one report to the next.

    Raises:
        ReportError: There is no run, or the runs are not over the same tasks.
    """
    entries = [
        Entry(read_run(path), read_results(path))
        for path in sorted(folder.iterdir())
        if (path / RUN_FILE).is_file()
    ]
    if not entries:
        raise ReportError(f"no run under {folder}")
    entries.sort(key=lambda e: (e.run.label.casefold(), e.run.checker))
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
            if first.run.label != second.run.label:
                continue
            answers = {(r.case, r.direction): r.answer for r in second.results}
            pairs = [(r.answer, answers[r.case, r.direction]) for r in first.results]
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
    """The ids of the cases whose ``case.json`` lists the feature."""
    found = set()
    for path in corpus.rglob("case.json"):
        if feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            found.add(path.parent.relative_to(corpus).as_posix())
    return frozenset(found)
