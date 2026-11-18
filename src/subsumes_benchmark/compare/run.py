"""Running one checker over the tasks of the corpus."""

import json
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

from subsumes_benchmark.compare.checkers import Checker, Dialect, Reply, Worker
from subsumes_benchmark.compare.downgrade import UnsupportedError, downgrade
from subsumes_benchmark.compare.results import RESULTS_FILE, Result, Run, result_line, write_run
from subsumes_benchmark.compare.witness import confirm
from subsumes_benchmark.generated.case import CaseSpec

if TYPE_CHECKING:
    from collections.abc import Sequence

    from subsumes_benchmark.compare.tasks import Task

# A warm-up task is not measured, so it need not be given the full time either.
WARMUP_TIMEOUT_SECONDS = 2.0


def prepare(task: Task, dialect: Dialect, scratch: Path) -> tuple[Path, Path]:
    """The two files to hand to a checker of the given dialect, written to ``scratch``.

    The first is the schema asked to accept everything, which is ``b`` of the case when the
    task asks the other direction. A checker of draft 2020-12 gets each schema as text
    indented like the rest of the corpus.

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
    paths = []
    for name, schema in schemas.items():
        match dialect:
            case "2020-12":
                text = json.dumps(schema, indent=2, allow_nan=False) + "\n"
            case "draft-07" | "draft-04":
                text = json.dumps(downgrade(schema, dialect), ensure_ascii=True)
            case _:
                assert_never(dialect)
        path = scratch / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths[0], paths[1]


def ask(worker: Worker, task: Task, scratch: Path, timeout: float) -> Reply:
    try:
        a, b = prepare(task, worker.checker.dialect, scratch)
    except UnsupportedError as exc:
        return Reply("unsupported", None, 0.0, str(exc))
    except RecursionError:
        return Reply("unsupported", None, 0.0, "the schema nests too deeply to rewrite")
    return worker.ask(a, b, timeout)


def _git(*args: str) -> str | None:
    done = subprocess.run(
        ["git", *args], cwd=Path(__file__).parent, capture_output=True, text=True, check=False
    )
    return done.stdout.strip() if done.returncode == 0 else None


def _revision(corpus: Path) -> str:
    """What ``git describe`` says about the checkout, or the version where there is none.

    ``-dirty`` is added when the corpus itself differs from what is committed; other
    uncommitted changes do not change what is measured.
    """
    described = _git("describe", "--tags", "--always")
    if not described:
        return "v" + version("subsumes-benchmark")
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
    started = datetime.now(UTC)
    clock = time.perf_counter()
    pending: queue.SimpleQueue[Task] = queue.SimpleQueue()
    for task in tasks:
        pending.put(task)
    done: queue.SimpleQueue[Result | BaseException] = queue.SimpleQueue()

    def work(number: int) -> None:
        try:
            with (
                tempfile.TemporaryDirectory(prefix=f"{checker.name}-") as scratch,
                (out / f"adapter-{number}.log").open("wb") as log,
            ):
                worker = Worker(checker, log)
                try:
                    for task in tasks[:warmup]:
                        ask(worker, task, Path(scratch), min(timeout, WARMUP_TIMEOUT_SECONDS))
                    while True:
                        try:
                            task = pending.get_nowait()
                        except queue.Empty:
                            return
                        reply = ask(worker, task, Path(scratch), timeout)
                        # The validator is asked after the checker has answered, so that
                        # it is in no time that is measured.
                        given = reply.counterexample
                        witness = (
                            None
                            if given is None
                            else confirm(CaseSpec.read(task.file), task.direction, given.instance)
                        )
                        done.put(
                            Result(
                                case=task.case,
                                direction=task.direction,
                                expected=task.expected,
                                answer=reply.answer,
                                seconds=reply.seconds,
                                wall_seconds=reply.wall_seconds or None,
                                detail=reply.detail,
                                reason=reply.reason,
                                witness=witness,
                            )
                        )
                finally:
                    worker.close()
        except BaseException as exc:
            done.put(exc)
            raise

    threads = [threading.Thread(target=work, args=(n,), daemon=True) for n in range(jobs)]
    for thread in threads:
        thread.start()

    answers: Counter[str] = Counter()
    with (out / RESULTS_FILE).open("w", encoding="utf-8") as lines:
        for count in range(1, len(tasks) + 1):
            result = done.get()
            if isinstance(result, BaseException):
                raise result
            lines.write(result_line(result))
            answers[result.answer] += 1
            if count % 500 == 0 or count == len(tasks):
                lines.flush()
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
            checker=checker.name,
            label=checker.label,
            variant=checker.variant,
            version=checker.version,
            homepage=checker.homepage,
            dialect=checker.dialect,
            corpus=_revision(corpus),
            timeout=timeout,
            warmup=warmup,
            seed=seed,
            tasks=len(tasks),
            platform=platform.platform(),
            processor=_processor(),
            started=started.isoformat(timespec="seconds"),
            seconds=round(time.perf_counter() - clock, 1),
        ),
    )
