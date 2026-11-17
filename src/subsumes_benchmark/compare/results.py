"""What a run writes and a report reads: one line per task and one file about the run."""

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from subsumes_benchmark.compare.tasks import Direction

type Answer = Literal["yes", "no", "unknown", "unsupported", "error", "timeout", "crash"]
"""How a task ended.

- ``yes`` and ``no`` are the checker's answers.
- ``unknown``: the checker ran and declined to answer.
- ``unsupported``: the checker was not asked, because the schemas cannot be written in the
  draft it reads.
- ``error``: the checker failed, by an exception or by rejecting a schema.
- ``timeout``: the checker did not answer in time.
- ``crash``: the checker's process died.
"""

ANSWERS: Sequence[Answer] = get_args(Answer.__value__)

RESULTS_FILE = "results.jsonl"
RUN_FILE = "run.json"


@dataclass(frozen=True)
class Result:
    """How one checker did on one task.

    ``seconds`` is what the checker took as its adapter measured it, from the schemas as text
    to the answer, and ``wall_seconds`` what the runner waited. Both are ``None`` where the
    checker was not asked, and ``seconds`` also where it did not come back.
    """

    case: str
    direction: Direction
    expected: bool | None
    answer: Answer
    seconds: float | None
    wall_seconds: float | None
    detail: str | None = None

    @property
    def collection(self) -> str:
        return self.case.partition("/")[0]

    @property
    def answered(self) -> bool:
        return self.answer in ("yes", "no")

    @property
    def wrong(self) -> bool:
        """Whether the answer contradicts the corpus; declining never does."""
        return (
            self.answered and self.expected is not None and self.expected != (self.answer == "yes")
        )

    @property
    def correct(self) -> bool:
        return self.answered and self.expected is not None and not self.wrong


@dataclass(frozen=True)
class Run:
    """One checker's run over the corpus: what ran, on what, and under which limits.

    ``corpus`` is what ``git describe`` says about the commit the corpus was read from:
    ``v0.5.0`` for a release, ``v0.5.0-3-gabc1234`` for what came after one.
    """

    @property
    def name(self) -> str:
        """The label with the variant, as a report shows the checker."""
        return self.label if self.variant is None else f"{self.label} ({self.variant})"

    checker: str
    label: str
    variant: str | None
    version: str
    homepage: str
    dialect: str
    corpus: str
    timeout: float
    warmup: int
    seed: int
    tasks: int
    platform: str
    processor: str
    started: str
    seconds: float


def write_run(folder: Path, run: Run) -> None:
    (folder / RUN_FILE).write_text(json.dumps(asdict(run), indent=2) + "\n", encoding="utf-8")


def read_run(folder: Path) -> Run:
    return Run(**json.loads((folder / RUN_FILE).read_text(encoding="utf-8")))


def result_line(result: Result) -> str:
    return json.dumps(asdict(result), ensure_ascii=False) + "\n"


def read_results(folder: Path) -> Sequence[Result]:
    with (folder / RESULTS_FILE).open(encoding="utf-8") as lines:
        return [Result(**json.loads(line)) for line in lines if line.strip()]
