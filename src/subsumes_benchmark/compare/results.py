"""What a run writes and a report reads: one line per task and one file about the run."""

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, get_args

from subsumes_benchmark.compare.witness import Witness

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

    ``detail`` is a short text for a person. ``reason`` is what kind of reason the checker had
    to decline, where its adapter names one, and is what a report counts such tasks by.
    ``witness`` is the counterexample that the checker gave with a no, where it gave one, with
    what a validator made of it.
    """

    case: str
    direction: Direction
    expected: bool | None
    answer: Answer
    seconds: float | None
    wall_seconds: float | None
    detail: str | None = None
    reason: str | None = None
    witness: Witness | None = None

    @property
    def collection(self) -> str:
        return self.case.partition("/")[0]


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


def _result(line: str) -> Result:
    fields = json.loads(line)
    witness = fields.pop("witness", None)
    return Result(**fields, witness=None if witness is None else Witness(**witness))


def read_results(folder: Path) -> Sequence[Result]:
    with (folder / RESULTS_FILE).open(encoding="utf-8") as lines:
        return [_result(line) for line in lines if line.strip()]
