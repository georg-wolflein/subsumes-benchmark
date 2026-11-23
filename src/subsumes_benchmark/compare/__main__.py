"""The ``subsumes-benchmark`` command: unpack the corpus, run a checker, and report on runs.

``python -m subsumes_benchmark.compare`` is the same command. Every path it takes is relative
to the working directory, so that it runs the same from a checkout and as an installed package.
In a checkout it also derives labels from runs, for the questions that upstream leaves open.
"""

import argparse
import sys
from pathlib import Path

from subsumes_benchmark.archive import ArchiveError, unpack
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.diff import diff
from subsumes_benchmark.compare.run import run
from subsumes_benchmark.compare.summary import ReportError, read_entry
from subsumes_benchmark.compare.tasks import read_tasks, read_unlabelled, select
from subsumes_benchmark.config import ConfigError

# Deriving validates instances as the labels read a schema, which needs the validators of the
# `validation` group, and the report draws a plot, which needs matplotlib. A run needs neither,
# so each is imported only where its command is run.
lazy from subsumes_benchmark.compare.derive import derive
lazy from subsumes_benchmark.compare.report import report

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
    running.add_argument(
        "--unlabelled",
        action="store_true",
        help="ask the questions without a label, in both directions, in place of the tasks",
    )
    running.add_argument("--jobs", type=int, default=1, help="adapter processes side by side")
    running.add_argument("--no-build", action="store_true", help="the adapter is built already")

    reporting = commands.add_parser(
        "report",
        help="draw how fast the checkers of the runs in a folder are, and table their results",
        description="Writes the comparison of the runs to --out as comparison.json, and from "
        "it a plot for light and for dark pages and a table with a row for every checker as "
        "results.md, which it prints too. Given the comparison.json of an earlier report in "
        "place of the runs, it makes the plots and the table from that file again.",
    )
    reporting.add_argument(
        "source",
        type=Path,
        help="a folder with one folder per checker, or the comparison.json of an earlier report",
    )
    reporting.add_argument(
        "--out", type=Path, default=Path("comparison"), help="where the files of the report go"
    )

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

    deriving = commands.add_parser(
        "derive",
        help="derive labels from runs with --unlabelled, in a checkout of the repository",
        description="Writes derived.json, from which the build gives the cases their labels. "
        "It needs the validators of the `validation` dependency group, which a checkout has.",
    )
    deriving.add_argument(
        "runs", type=Path, nargs="+", help="the folder of a run with --unlabelled"
    )
    deriving.add_argument("--corpus", type=Path, default=CORPUS, help="the folder of the corpus")
    deriving.add_argument("--derived", type=Path, default=Path("derived.json"), help="the file")

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
    if args.command == "report":
        print(report(args.source, args.out))
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
            (read_unlabelled if args.unlabelled else read_tasks)(args.corpus),
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
        derive(args.corpus, args.derived, args.runs)


if __name__ == "__main__":
    main()
