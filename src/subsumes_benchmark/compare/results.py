"""What a run writes and a report reads: one line per task and one file about the run.

``schemas/result.schema.json`` and ``schemas/run.schema.json`` say what the two hold, and the
models that read and write them are generated from those. A result is one of seven classes,
one for each way that a task can end, and is told apart with ``match``. Here is what a
schema cannot say.
"""

from typing import TYPE_CHECKING, Literal, assert_never, get_args

from pydantic import TypeAdapter, ValidationError

from subsumes_benchmark.compare.tasks import collection_of
from subsumes_benchmark.config import ConfigError
from subsumes_benchmark.generated.result import (
    Crash,
    Error,
    No,
    ResultSpec,
    Timeout,
    Unknown,
    Unsupported,
    Yes,
)
from subsumes_benchmark.generated.run import RunSpec

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

type Result = ResultSpec
"""How one checker did on one task: a line of ``results.jsonl``."""

type Ending = Literal["yes", "no", "unknown", "error", "timeout", "unsupported", "crash"]
"""How a task ended, in a word.

- ``yes`` and ``no`` are the checker's answers.
- ``unknown``: the checker ran and declined to answer.
- ``error``: the checker failed, by an exception or by rejecting a schema.
- ``timeout``: the checker did not answer in time.
- ``unsupported``: the checker was not asked, because the schemas cannot be written in the
  draft it reads.
- ``crash``: the adapter is at fault: its process died, or gave a line that is no reply.
"""

ENDINGS: Sequence[Ending] = get_args(Ending.__value__)

RESULTS_FILE = "results.jsonl"
RUN_FILE = "run.json"

_RESULT: TypeAdapter[Result] = TypeAdapter(ResultSpec)


def ending(result: Result) -> Ending:
    match result:
        case Yes():
            return "yes"
        case No():
            return "no"
        case Unknown():
            return "unknown"
        case Error():
            return "error"
        case Timeout():
            return "timeout"
        case Unsupported():
            return "unsupported"
        case Crash():
            return "crash"
        case _:
            assert_never(result)


def collection(result: Result) -> str:
    """The collection of the task: the folders of the id of its case, an origin and a name."""
    return collection_of(result.case)


def seconds(result: Result) -> float | None:
    """What the checker took, where it has a time: it ran, and it came back."""
    match result:
        case Yes() | No() | Unknown() | Error():
            return result.seconds
        case Timeout() | Unsupported() | Crash():
            return None
        case _:
            assert_never(result)


class Run(RunSpec):
    """One checker's run over the corpus: the ``run.json`` of a run."""

    @property
    def title(self) -> str:
        """The label of the checker with its variant, as a report shows the checker."""
        checker = self.checker
        return checker.label if checker.variant is None else f"{checker.label} ({checker.variant})"


def write_run(folder: Path, run: Run) -> None:
    # A key that does not apply is left out, and the checker has its `$schema` under that name.
    text = run.model_dump_json(indent=2, by_alias=True, exclude_unset=True)
    (folder / RUN_FILE).write_text(text + "\n", encoding="utf-8")


def read_run(folder: Path) -> Run:
    return Run.read(folder / RUN_FILE)


def result_line(result: Result) -> str:
    """The result as a line of the file. A key that does not apply is left out."""
    return result.model_dump_json(exclude_unset=True) + "\n"


def read_results(folder: Path) -> Sequence[Result]:
    """The results of a run, in the order in which they were written.

    Raises:
        ConfigError: A line is not what the schema of a result says.
    """
    path = folder / RESULTS_FILE
    found = []
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                found.append(_RESULT.validate_json(line))
            except ValidationError as error:
                raise ConfigError(f"{path}, line {number}: {error}") from error
    return found
