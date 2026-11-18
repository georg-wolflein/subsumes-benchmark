"""Running one checker over the tasks of the corpus."""

import platform
import queue
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, assert_never, cast

from subsumes_benchmark.compare.checkers import Checker, Crashed, Dialect, Worker
from subsumes_benchmark.compare.downgrade import UnsupportedError, downgrade
from subsumes_benchmark.compare.results import (
    RESULTS_FILE,
    Result,
    Run,
    ending,
    result_line,
    write_run,
)
from subsumes_benchmark.compare.witness import confirm
from subsumes_benchmark.generated import reply as replies, result as results
from subsumes_benchmark.generated.case import CaseSpec
from subsumes_benchmark.generated.run import Checker as CheckerOfRun

if TYPE_CHECKING:
    from collections.abc import Sequence

    from subsumes_benchmark import Json
    from subsumes_benchmark.compare.tasks import Task
    from subsumes_benchmark.generated.reply import ReplySpec
    from subsumes_benchmark.generated.request import Schema

# At most this many characters of what an adapter says for a person are kept.
MESSAGE_LENGTH = 500
# A warm-up task is not measured, so it need not be given the full time either.
WARMUP_TIMEOUT_SECONDS = 2.0


def prepare(task: Task, dialect: Dialect) -> tuple[Schema, Schema]:
    """The two schemas to hand to a checker of the given dialect.

    The first is the schema asked to accept everything, which is ``b`` of the case when the
    task asks the other direction. A checker of draft 2020-12 gets each schema as the
    corpus has it, and one of an older draft gets it rewritten to that draft.

    Raises:
        UnsupportedError: The dialect cannot express one of the schemas.
    """
    case = CaseSpec.read(task.file)
    match task.direction:
        case "a_subsumes_b":
            schemas = {"a": case.a, "b": case.b}
        case "b_subsumes_a":
            schemas = {"a": case.b, "b": case.a}
        case _:
            assert_never(task.direction)
    match dialect:
        case "2020-12":
            return schemas["a"], schemas["b"]
        case "draft-07" | "draft-04":
            older = (downgrade(schemas["a"], dialect), downgrade(schemas["b"], dialect))
            return cast("tuple[Schema, Schema]", older)
        case _:
            assert_never(dialect)


@dataclass(frozen=True)
class NotAsked:
    """The checker was not asked, because its draft cannot express one of the schemas."""

    message: str


def ask(worker: Worker, task: Task, timeout: float) -> tuple[ReplySpec | Crashed | NotAsked, float]:
    """What came back for a task, and the seconds that the runner waited for it."""
    try:
        a, b = prepare(task, worker.checker.dialect)
    except UnsupportedError as exc:
        return NotAsked(str(exc)), 0.0
    except RecursionError:
        return NotAsked("the schema nests too deeply to rewrite"), 0.0
    return worker.ask(a, b, timeout)


def result(task: Task, came: ReplySpec | Crashed | NotAsked, wall_seconds: float) -> Result:
    """How the task ended: what came back for it, as a line of the results.

    A key that does not apply is not set, so that it is left out of the line. The validator
    is asked about the counterexample of a no here, after the checker has answered, so that
    it is in no time that is measured.
    """
    said: dict[str, Json] = {"case": task.case, "direction": task.direction}
    said["expected"] = task.expected
    match came:
        case NotAsked():
            said |= {"failure": "unsupported", "message": came.message}
            return results.Unsupported.model_validate(said)
        case Crashed():
            said |= {"failure": "crash", "message": came.message[:MESSAGE_LENGTH]}
            return results.Crash.model_validate(said | {"wall_seconds": wall_seconds})
        case replies.Timeout():
            said |= {"failure": "timeout", "wall_seconds": wall_seconds}
            return results.Timeout.model_validate(said)
        case replies.Error():
            said |= {"failure": "error", "message": came.message[:MESSAGE_LENGTH]}
            if came.seconds is not None:
                said["seconds"] = came.seconds
            return results.Error.model_validate(said | {"wall_seconds": wall_seconds})
        case replies.Yes():
            said |= {"answer": True, "seconds": came.seconds, "wall_seconds": wall_seconds}
            return results.Yes.model_validate(said)
        case replies.Unknown():
            said |= {"answer": None, "seconds": came.seconds, "wall_seconds": wall_seconds}
            if came.reason is not None:
                said["reason"] = came.reason
            if came.message is not None:
                said["message"] = came.message[:MESSAGE_LENGTH]
            return results.Unknown.model_validate(said)
        case replies.No():
            said |= {"answer": False, "seconds": came.seconds, "wall_seconds": wall_seconds}
            if came.message is not None:
                said["message"] = came.message[:MESSAGE_LENGTH]
            no = results.No.model_validate(said)
            # The key and not its value says whether there is one: ``null`` is an instance.
            if "counterexample" not in came.model_fields_set:
                return no
            witness = confirm(CaseSpec.read(task.file), task.direction, came.counterexample)
            return no.model_copy(update={"witness": witness})
        case _:
            assert_never(came)


# The root of the repository, where this file is in a checkout of it.
CHECKOUT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=CHECKOUT, capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def _revision(corpus: Path) -> str:
    """What the corpus is: a release, or what ``git describe`` says about a checkout.

    The package of a version holds the corpus of that version, and an unpacked corpus does not
    say which one it is. So the corpus is taken to be the release that the package is of, as
    ``v0.5.0``. Only where the package runs from a checkout of the repository, over the corpus
    of that checkout, is it what ``git describe`` says, with ``-dirty`` where the corpus
    differs from what is committed; other uncommitted changes do not change what is measured.
    """
    released = "v" + version("subsumes-benchmark")
    in_checkout = (CHECKOUT / ".git").exists() and corpus.resolve() == CHECKOUT / "corpus"
    described = _git("describe", "--tags", "--always") if in_checkout else None
    if not described:
        return released
    changed = _git("status", "--porcelain", "--", str(corpus.resolve()))
    return described + ("-dirty" if changed else "")


def _processor() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or platform.machine()


def run(
    checker: Checker,
    tasks: Sequence[Task],
    out: Path,
    *,
    corpus: Path,
    timeout: float,
    warmup: int,
    seed: int,
    jobs: int,
) -> None:
    """Run the checker on every task and write the results to ``out``.

    Args:
        checker: The checker, its adapter already built.
        tasks: The tasks, in the order to run them.
        out: The folder for ``results.jsonl``, ``run.json`` and the adapter's log.
        corpus: The folder the tasks were read from, for the record of what was measured.
        timeout: The seconds a checker may take for one task.
        warmup: How many of the first tasks each adapter process answers before anything
            is measured, so that a JIT compiler has seen the code.
        seed: The seed the order of the tasks was drawn with, for the record.
        jobs: How many adapter processes run side by side. More than one is quicker and
            makes the times less exact.
    """
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC).replace(microsecond=0)
    clock = time.perf_counter()
    pending: queue.SimpleQueue[Task] = queue.SimpleQueue()
    for task in tasks:
        pending.put(task)
    done: queue.SimpleQueue[Result | BaseException] = queue.SimpleQueue()

    def work(number: int) -> None:
        try:
            with (out / f"adapter-{number}.log").open("wb") as log:
                worker = Worker(checker, log)
                try:
                    for task in tasks[:warmup]:
                        ask(worker, task, min(timeout, WARMUP_TIMEOUT_SECONDS))
                    while True:
                        try:
                            task = pending.get_nowait()
                        except queue.Empty:
                            return
                        done.put(result(task, *ask(worker, task, timeout)))
                finally:
                    worker.close()
        except BaseException as exc:
            done.put(exc)
            raise

    threads = [threading.Thread(target=work, args=(n,), daemon=True) for n in range(jobs)]
    for thread in threads:
        thread.start()

    answers: Counter[str] = Counter()
    # A line is written when it is there, so that a run that is stopped keeps its answers.
    with (out / RESULTS_FILE).open("w", encoding="utf-8", buffering=1) as lines:
        for count in range(1, len(tasks) + 1):
            ended = done.get()
            if isinstance(ended, BaseException):
                raise ended
            lines.write(result_line(ended))
            answers[ending(ended)] += 1
            if count % 500 == 0 or count == len(tasks):
                elapsed = time.perf_counter() - clock
                summary = ", ".join(f"{n} {answer}" for answer, n in sorted(answers.items()))
                print(
                    f"{checker.name}: {count}/{len(tasks)} after {elapsed:.0f} s ({summary})",
                    file=sys.stderr,
                    flush=True,
                )
    for thread in threads:
        thread.join()

    write_run(
        out,
        Run(
            name=checker.name,
            # The checker as its file describes it, with nothing set that the file leaves out.
            checker=CheckerOfRun.model_validate(
                checker.model_dump(by_alias=True, exclude_unset=True)
            ),
            corpus=_revision(corpus),
            timeout=timeout,
            warmup=warmup,
            seed=seed,
            jobs=jobs,
            tasks=len(tasks),
            platform=platform.platform(),
            processor=_processor(),
            started=started,
            wall_seconds=round(time.perf_counter() - clock, 1),
        ),
    )
