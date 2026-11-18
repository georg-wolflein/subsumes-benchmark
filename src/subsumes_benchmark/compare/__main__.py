"""The ``subsumes-benchmark`` command: unpack the corpus, run a checker, and report on runs.

``python -m subsumes_benchmark.compare`` is the same command. Every path it takes is relative
to the working directory, so that it runs the same from a checkout and as an installed package.
"""

import argparse
import sys
from pathlib import Path

from subsumes_benchmark.archive import ArchiveError, unpack
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.diff import diff
from subsumes_benchmark.compare.run import run
from subsumes_benchmark.compare.summary import ReportError, read_entry
from subsumes_benchmark.compare.tasks import read_tasks, select
from subsumes_benchmark.config import ConfigError

CORPUS = Path("corpus")


def main() -> None:
    try:
        _main()
    except (ArchiveError, ConfigError, ReportError) as error:
        sys.exit(str(error))


def _main() -> None:
    parser = argparse.ArgumentParser(prog="subsumes-benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    unpacking = commands.add_parser(
        "corpus",
        help="unpack the corpus that the package holds",
        description="The corpus is the one of the release that the package is of.",
    )
    unpacking.add_argument("folder", type=Path, help="where it goes: a new folder, or an empty one")

    running = commands.add_parser(
        "run",
        help="run one checker over the corpus",
        description="Writes the results to a folder under --out that is named like the folder "
        "of the checker.",
    )
    running.add_argument("checker", type=Path, help="the folder of a checker.json")
    running.add_argument("--out", type=Path, default=Path("results"), help="where results go")
    running.add_argument("--corpus", type=Path, default=CORPUS, help="the folder of the corpus")
    running.add_argument("--timeout", type=float, default=10.0, help="seconds per task")
    running.add_argument("--warmup", type=int, default=200, help="unmeasured tasks first")
    running.add_argument("--limit", type=int, help="run only this many tasks, a random sample")
    running.add_argument("--collection", action="append", default=[], help="only this one")
    running.add_argument("--seed", type=int, default=0, help="of the order of the tasks")
    running.add_argument("--jobs", type=int, default=1, help="adapter processes side by side")
    running.add_argument("--no-build", action="store_true", help="the adapter is built already")

    reporting = commands.add_parser("report", help="report on the runs in a folder")
    reporting.add_argument("results", type=Path, help="a folder with one folder per checker")
    reporting.add_argument("--out", type=Path, default=Path("comparison"), help="where it goes")
    reporting.add_argument("--corpus", type=Path, default=CORPUS, help="the folder of the corpus")
    reporting.add_argument("--readme", type=Path, help="a README whose marked part to rewrite")

    differing = commands.add_parser(
        "diff",
        help="hold one run of a checker against an earlier one, as a comment for a pull request",
        description="Fails when an answer is wrong, when a task ended in an error, a crash or a "
        "timeout, and when a task that the base answered is no longer answered.",
    )
    differing.add_argument("results", type=Path, help="the folder of a run, as `run` wrote it")
    differing.add_argument("--base", type=Path, help="the folder of the run to compare with")
    differing.add_argument("--base-label", help="what the comment calls the base, such as a commit")
    differing.add_argument(
        "--allow-lost", action="store_true", help="pass with tasks that are no longer answered"
    )
    differing.add_argument(
        "--lost-hint", help="what the comment says about such tasks, such as how to accept them"
    )
    differing.add_argument("--out", type=Path, help="write the comment here, not to the terminal")

    args = parser.parse_args()
    if args.command == "corpus":
        unpack(args.folder)
        return
    if args.command == "diff":
        found = diff(
            read_entry(args.results),
            None if args.base is None else read_entry(args.base),
            base_label=args.base_label,
            allow_lost=args.allow_lost,
            lost_hint=args.lost_hint,
        )
        if args.out is None:
            sys.stdout.write(found.comment)
        else:
            args.out.write_text(found.comment, encoding="utf-8")
        if found.failures:
            print(f"{found.failures} wrong answers or failed tasks", file=sys.stderr)
        if found.lost and not args.allow_lost:
            print(f"{found.lost} tasks of the base are no longer answered", file=sys.stderr)
        if found.failures or (found.lost and not args.allow_lost):
            sys.exit(1)
        return
    if not args.corpus.is_dir():
        sys.exit(
            f"there is no corpus at {args.corpus}; `subsumes-benchmark corpus {args.corpus}` "
            "unpacks the one of the package there, and --corpus names another folder"
        )
    if args.command == "run":
        # The run is named like the folder, and a path such as `.` has no name.
        checker = Checker.load(args.checker.resolve())
        if not args.no_build:
            checker.compile()
        tasks = select(
            read_tasks(args.corpus),
            collections=args.collection,
            limit=args.limit,
            seed=args.seed,
        )
        run(
            checker,
            tasks,
            args.out / checker.name,
            corpus=args.corpus,
            timeout=args.timeout,
            warmup=args.warmup,
            seed=args.seed,
            jobs=args.jobs,
        )
    else:
        # The report draws charts, which needs matplotlib; a run does not.
        from subsumes_benchmark.compare.report import report  # noqa: PLC0415

        report(args.results, args.out, args.corpus, args.readme)


if __name__ == "__main__":
    main()
