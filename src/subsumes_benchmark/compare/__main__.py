"""``python -m subsumes_benchmark.compare``: run a checker, or report on the runs."""

import argparse
from pathlib import Path

from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.compare.run import run
from subsumes_benchmark.compare.tasks import read_tasks, select

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m subsumes_benchmark.compare")
    commands = parser.add_subparsers(dest="command", required=True)

    running = commands.add_parser("run", help="run one checker over the corpus")
    running.add_argument("checker", help="the name of a folder under checkers/")
    running.add_argument("--out", type=Path, default=ROOT / "results", help="where results go")
    running.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    running.add_argument("--timeout", type=float, default=10.0, help="seconds per task")
    running.add_argument("--warmup", type=int, default=200, help="unmeasured tasks first")
    running.add_argument("--limit", type=int, help="run only this many tasks, a random sample")
    running.add_argument("--collection", action="append", default=[], help="only this one")
    running.add_argument("--seed", type=int, default=0, help="of the order of the tasks")
    running.add_argument("--jobs", type=int, default=1, help="adapter processes side by side")
    running.add_argument("--no-build", action="store_true", help="the adapter is built already")

    reporting = commands.add_parser("report", help="report on the runs in a folder")
    reporting.add_argument("results", type=Path, help="a folder with one folder per checker")
    reporting.add_argument("--out", type=Path, default=ROOT / "comparison", help="where it goes")
    reporting.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    reporting.add_argument("--readme", type=Path, help="a README whose marked part to rewrite")

    args = parser.parse_args()
    if args.command == "run":
        checker = Checker.load(ROOT / "checkers" / args.checker)
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
        # The report draws charts, which needs more than the standard library; a run does not.
        from subsumes_benchmark.compare.report import report  # noqa: PLC0415

        report(args.results, args.out, args.corpus, args.readme)


main()
