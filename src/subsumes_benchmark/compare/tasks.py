"""The questions of the corpus, one task per question."""

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from subsumes_benchmark.generated.case import CaseSpec, Schema
from subsumes_benchmark.generated.result import Direction


@dataclass(frozen=True)
class Task:
    """One question about the two schemas of a case, which ``file`` holds.

    For the direction ``b_subsumes_a`` the two schemas are swapped when the checker is asked,
    so that it is always asked whether its first schema accepts every instance valid under
    its second.
    """

    case: str
    direction: Direction
    file: Path
    expected: bool | None

    @property
    def collection(self) -> str:
        return collection_of(self.case)


def collection_of(case: str) -> str:
    """The collection of a case, as its folder below the corpus: its origin and its name."""
    return case.rpartition("/")[0]


def case_files(corpus: Path) -> Mapping[str, Path]:
    """The file of every case by its id, sorted by the folders and the name of the case.

    A case is every JSON file in the folder of a collection, which is a folder in the folder
    of an origin. Its id is its path below the corpus without the extension.
    """
    found = {
        path.relative_to(corpus).as_posix().removesuffix(".json"): path
        for path in corpus.glob("*/*/*.json")
    }
    return {case: found[case] for case in sorted(found, key=lambda case: case.split("/"))}


def answer(case: CaseSpec, direction: Direction) -> bool | None:
    """The answer that the label of a case gives in one direction, or ``None`` where it has none."""
    match direction:
        case "a_subsumes_b":
            label = case.labels.a_subsumes_b
        case "b_subsumes_a":
            label = case.labels.b_subsumes_a
        case _:
            assert_never(direction)
    return None if label is None else label.answer


def read_tasks(corpus: Path) -> Sequence[Task]:
    """Every task of the corpus, sorted by case: two for each case, one in each direction.

    Both are asked also where the corpus claims nothing, since how often a checker answers
    can be measured without a label. Only a task with a label can be solved.
    """
    found = []
    for case, path in case_files(corpus).items():
        known = CaseSpec.read(path)
        found.append(Task(case, "a_subsumes_b", path, answer(known, "a_subsumes_b")))
        found.append(Task(case, "b_subsumes_a", path, answer(known, "b_subsumes_a")))
    return found


def read_unlabelled(corpus: Path) -> Sequence[Task]:
    """Every question that the corpus has no label for, sorted by case.

    These are what a run asks that is to find labels, where ``read_tasks`` gives what a run
    asks that is to measure a checker. A case's other direction is left out where the
    corpus asks that question already: as the first direction of a case, which is this very
    case when its two schemas are the same.
    """
    files = case_files(corpus)
    cases = {case: CaseSpec.read(path) for case, path in files.items()}
    asked = {(_digest(known.a), _digest(known.b)) for known in cases.values()}
    found = []
    for case, known in cases.items():
        if known.labels.a_subsumes_b is None:
            found.append(Task(case, "a_subsumes_b", files[case], None))
        mirrored = (_digest(known.b), _digest(known.a))
        if known.labels.b_subsumes_a is None and mirrored not in asked:
            found.append(Task(case, "b_subsumes_a", files[case], None))
    return found


def _digest(schema: Schema) -> bytes:
    """What tells a schema from every other one: two that are the same JSON value have the same."""
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).digest()


def select(
    tasks: Sequence[Task],
    *,
    collections: Sequence[str] = (),
    limit: int | None = None,
    seed: int = 0,
) -> Sequence[Task]:
    """The tasks to run, in the order to run them.

    The order is random but the same for every checker, so that what depends on the order
    (a warm-up, a cache, a machine that slows down) does not fall on one collection. A limit
    keeps the first tasks of that order, which is a sample across all collections.
    """
    chosen = [task for task in tasks if not collections or task.collection in collections]
    random.Random(seed).shuffle(chosen)
    return chosen if limit is None else chosen[:limit]
