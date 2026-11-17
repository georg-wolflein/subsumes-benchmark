"""The questions of the corpus, one task per question."""

import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

type Direction = Literal["a_subsumes_b", "b_subsumes_a"]


@dataclass(frozen=True)
class Task:
    """One question: does ``a`` accept every instance valid under ``b``?

    For the direction ``b_subsumes_a`` the two files of the case are swapped, so that ``a``
    is always the schema asked to accept everything.
    """

    case: str
    direction: Direction
    a: Path
    b: Path
    expected: bool | None

    @property
    def collection(self) -> str:
        return self.case.partition("/")[0]


def _label(value: object) -> bool | None:
    assert value is None or isinstance(value, bool)
    return value


def read_tasks(corpus: Path) -> Sequence[Task]:
    """Every task of the corpus, sorted by case.

    A case always asks whether A subsumes B, also where the corpus claims nothing, since
    how often a checker answers and how long it takes can be measured without a label. It
    asks the other direction only where the corpus has a label for it.
    """
    found = []
    for path in sorted(corpus.rglob("case.json")):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        folder = path.parent
        case = folder.relative_to(corpus).as_posix()
        a, b = folder / "a.json", folder / "b.json"
        found.append(Task(case, "a_subsumes_b", a, b, _label(metadata["a_subsumes_b"])))
        reverse = _label(metadata["b_subsumes_a"])
        if reverse is not None:
            found.append(Task(case, "b_subsumes_a", b, a, reverse))
    return found


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
