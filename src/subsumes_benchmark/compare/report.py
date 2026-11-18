"""Writing the report on a set of runs: ``report.md`` and a chart for light and dark pages.

The chart is drawn with matplotlib, which the ``report`` dependency group brings; a run
does not need it.
"""

import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_hex, to_rgb
from matplotlib.patches import Patch, Rectangle

from subsumes_benchmark.compare.summary import (
    LABELLED,
    OUTCOME_NAMES,
    UNLABELLED,
    Entry,
    Outcome,
    agreements,
    cases_using,
    has_label,
    read_entries,
)
from subsumes_benchmark.compare.tasks import read_tasks

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from matplotlib.artist import Artist
    from matplotlib.axes import Axes

    from subsumes_benchmark.compare.results import Result

REPORT_FILE = "report.md"
CHART_FILES = {"light": "chart-light.svg", "dark": "chart-dark.svg"}
# The part of the README that a report rewrites lies between these two lines.
README_START = "<!-- comparison:start -->"
README_END = "<!-- comparison:end -->"

NOTHING = "—"
LINE_STYLES = ("solid", (0, (4, 2)), (0, (1, 2)))
# How many steps a curve of the chart keeps; more would only make the file larger.
STEPS = 250


@dataclass(frozen=True)
class Theme:
    """The colours of the chart on one kind of page."""

    surface: str
    ink: str
    secondary: str
    muted: str
    grid: str
    axis: str
    # One per checker label, in the order the labels are listed; never cycled.
    series: Sequence[str]
    # One for each way that a task with a label can end.
    outcomes: Mapping[Outcome, str]
    # From no task solved to every task solved.
    ramp: Sequence[str]


LIGHT = Theme(
    surface="#fcfcfb",
    ink="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
    outcomes={
        "correct": "#0ca30c",
        "wrong_no": "#ec835a",
        "wrong_yes": "#d03b3b",
        "no_answer": "#c3c2b7",
        "timeout": "#e1e0d9",
    },
    ramp=("#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"),
)
DARK = Theme(
    surface="#1a1a19",
    ink="#f0efec",
    secondary="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    series=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"),
    outcomes={
        "correct": "#0ca30c",
        "wrong_no": "#ec835a",
        "wrong_yes": "#d03b3b",
        "no_answer": "#52514e",
        "timeout": "#383835",
    },
    ramp=("#0d366b", "#184f95", "#256abf", "#3987e5", "#86b6ef"),
)
THEMES: Mapping[str, Theme] = {"light": LIGHT, "dark": DARK}


# --------------------------------------------------------------------------- words and numbers


def count(n: int) -> str:
    return f"{n:,}"


def share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else NOTHING


def duration(seconds: float | None) -> str:
    if seconds is None:
        return NOTHING
    if seconds < 0.001:
        return f"{seconds * 1e6:.0f} µs"
    if seconds < 1:
        return f"{seconds * 1e3:.1f} ms" if seconds < 0.1 else f"{seconds * 1e3:.0f} ms"
    if seconds < 120:
        return f"{seconds:.1f} s"
    return f"{seconds / 60:.0f} min"


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A markdown table whose first column is text and whose other columns are numbers."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] + ["---:"] * (len(headers) - 1)) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# --------------------------------------------------------------------------- the chart


def _text_on(fill: str) -> str:
    """White or near-black, whichever reads on the fill."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in to_rgb(fill))
    return LIGHT.ink if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.3 else "#ffffff"


def _bare(ax: Axes) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)


def _outcomes(ax: Axes, entries: Sequence[Entry], theme: Theme) -> None:
    """One bar per checker, split by how its tasks with a label ended."""
    _bare(ax)
    for row, entry in enumerate(entries):
        counts, total = entry.counts(has_label), len(entry.labelled())
        left = 0.0
        for kind in LABELLED:
            width = counts[kind] / total if total else 0
            if width == 0:
                continue
            fill = theme.outcomes[kind]
            # The surface-coloured edge is the gap between two segments.
            ax.barh(row, width, left=left, height=0.62, color=fill, edgecolor=theme.surface, lw=2)
            if width >= 0.05:
                ax.text(left + 0.008, row, f"{100 * width:.0f}%", va="center", ha="left",
                        fontsize=8.5, color=_text_on(fill))  # fmt: skip
            left += width
        ax.text(1.012, row, f"{share(entry.solved(), total)} solved", va="center", ha="left",
                fontsize=9.5, color=theme.ink)  # fmt: skip
    ax.set_xlim(0, 1)
    ax.set_ylim(len(entries) - 0.5, -0.5)
    ax.set_xticks([])
    ax.set_yticks(range(len(entries)), [entry.name for entry in entries])
    ax.tick_params(axis="y", labelcolor=theme.ink, labelsize=10, pad=6)


def _tick(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1e6:g} µs"
    return f"{seconds * 1e3:g} ms" if seconds < 1 else f"{seconds:g} s"


def _thinned(seconds: Sequence[float], total: int) -> tuple[list[float], list[float]]:
    """The steps of a cumulative curve, a few hundred of them however many tasks there are."""
    stride = max(1, len(seconds) // STEPS)
    kept = sorted({*range(stride - 1, len(seconds), stride), len(seconds) - 1} - {-1})
    return [seconds[i] for i in kept], [(i + 1) / total for i in kept]


def _speed(ax: Axes, entries: Sequence[Entry], theme: Theme, styles: Mapping[str, tuple]) -> None:
    """For every checker, the share of the tasks with a label it solved within a time."""
    timeout = entries[0].run.timeout
    # The axis starts at the power of ten below all but the very fastest tasks.
    early = min(
        (seconds[len(seconds) // 100] for e in entries if (seconds := e.solved_seconds())),
        default=timeout / 10,
    )
    lowest = 10.0**-6
    while lowest * 10 <= early:
        lowest *= 10
    for entry in entries:
        seconds = [max(s, lowest) for s in entry.solved_seconds()]
        # Nothing is solved where nothing has a label, so the curve then stays at zero.
        total = len(entry.labelled()) or 1
        xs, ys = _thinned(seconds, total)
        colour, line = styles[entry.name]
        ax.step([lowest, *xs, timeout], [0.0, *ys, len(seconds) / total], where="post",
                color=colour, lw=2, ls=line, label=entry.name)  # fmt: skip
    ax.set_xscale("log")
    ax.set_xlim(lowest, timeout)
    ax.set_ylim(0, 1)
    ticks = [lowest]
    while ticks[-1] * 10 <= timeout * 1.0001:
        ticks.append(ticks[-1] * 10)
    ax.set_xticks(ticks, [_tick(t) for t in ticks])
    ax.minorticks_off()
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", color=theme.grid, lw=0.8)
    ax.set_axisbelow(True)
    _bare(ax)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(theme.axis)
    ax.tick_params(labelcolor=theme.muted, labelsize=9)
    ax.tick_params(axis="x", pad=6)
    ax.set_xlabel("time for one task", color=theme.secondary, fontsize=9.5)


def _collections(ax: Axes, entries: Sequence[Entry], theme: Theme) -> None:
    """A cell per checker and collection: the share solved of its tasks with a label.

    A collection of a sample that has no such task gets cells of the surface, without a share.
    """
    _bare(ax)
    shades = LinearSegmentedColormap.from_list("solved", list(theme.ramp))
    by_entry = [entry.collections() for entry in entries]
    names = list(by_entry[0])
    for row, name in enumerate(names):
        for column, solved in enumerate(by_entry):
            done, tasks = solved[name]
            if not tasks:
                continue
            fill = to_hex(shades(done / tasks))
            ax.add_patch(
                Rectangle((column, row), 1, 1, facecolor=fill, edgecolor=theme.surface, lw=2)
            )
            ax.text(column + 0.5, row + 0.5, f"{100 * done / tasks:.0f}", ha="center", va="center",
                    fontsize=9.5, color=_text_on(fill))  # fmt: skip
    ax.set_xlim(0, len(entries))
    ax.set_ylim(len(names), 0)
    ax.xaxis.tick_top()
    ax.set_xticks(
        [column + 0.5 for column in range(len(entries))],
        ["\n".join(textwrap.wrap(entry.name, 13)) for entry in entries],
    )
    ax.set_yticks(
        [row + 0.5 for row in range(len(names))],
        [f"{name}  ({count(by_entry[0][name][1])})" for name in names],
    )
    ax.tick_params(axis="x", labelcolor=theme.secondary, labelsize=8.5, pad=4)
    ax.tick_params(axis="y", labelcolor=theme.ink, labelsize=9.5, pad=6)


def draw(entries: Sequence[Entry], theme: Theme, caption: str, path: Path) -> None:
    """Draw the chart of a report: outcomes on top, speed and collections below.

    The file is an SVG, or what the suffix of ``path`` names.
    """
    labels = list(dict.fromkeys(entry.run.label for entry in entries))
    if len(labels) > len(theme.series):
        raise ValueError(
            f"the chart has colours for {len(theme.series)} checkers, not {len(labels)}"
        )
    # A colour per label and a line per variant, so that variants of a checker look alike.
    styles: dict[str, tuple] = {}
    for label, colour in zip(labels, theme.series, strict=False):
        variants = [entry for entry in entries if entry.run.label == label]
        for variant, line in zip(variants, LINE_STYLES, strict=False):
            styles[variant.name] = (colour, line)

    settings: dict[str, object] = {
        # Text stays text, so the file is small and is set in the reader's own sans-serif.
        "svg.fonttype": "none",
        "svg.hashsalt": "subsumes-benchmark",
        "font.family": ["Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
        "font.sans-serif": ["DejaVu Sans"],
        "text.color": theme.ink,
        "axes.facecolor": theme.surface,
        "figure.facecolor": theme.surface,
        "savefig.facecolor": theme.surface,
    }
    # Everything is placed in inches from the top left corner, so that a chart of more
    # checkers grows downwards and nothing else moves.
    width = 11.5
    bars = 0.42 * len(entries)
    lower = 1.85 + bars  # where the heading of the two lower panels starts
    plot = lower + 1.3  # where their plots start
    height = plot + 3.1 + 1.05
    with mpl.rc_context(settings):  # ty: ignore[invalid-argument-type]
        fig = plt.figure(figsize=(width, height))

        def axes(left: float, top: float, wide: float, tall: float) -> Axes:
            return fig.add_axes(
                (left / width, 1 - (top + tall) / height, wide / width, tall / height)
            )

        def text(left: float, top: float, words: str, **style: object) -> None:
            fig.text(left / width, 1 - top / height, words, va="top", **style)  # ty: ignore[invalid-argument-type]

        def heading(left: float, top: float, title: str, subtitle: str) -> None:
            text(left, top, title, fontsize=12, fontweight="bold", color=theme.ink)
            text(left, top + 0.27, subtitle, fontsize=9.5, color=theme.secondary)

        def legend(handles: Sequence[Artist], left: float, top: float, columns: int) -> None:
            fig.legend(handles=list(handles), loc="upper left", ncol=columns, frameon=False,
                       bbox_to_anchor=(left / width, 1 - top / height), fontsize=9,
                       labelcolor=theme.secondary, handlelength=2.2, handleheight=1.0,
                       columnspacing=1.6, handletextpad=0.6, borderpad=0,
                       borderaxespad=0)  # fmt: skip

        heading(0.3, 0.3, "How every task with a label ended",
                "Share of the tasks with a label, by checker")  # fmt: skip
        legend(
            [Patch(facecolor=theme.outcomes[kind], label=OUTCOME_NAMES[kind]) for kind in LABELLED],
            2.3, 0.95, len(LABELLED),
        )  # fmt: skip
        outcomes = axes(2.3, 1.3, width - 2.3 - 1.3, bars)
        _outcomes(outcomes, entries, theme)

        heading(0.3, lower, "How fast the tasks are solved",
                "Share of the tasks with a label solved within a time")  # fmt: skip
        speed = axes(0.85, plot, 3.85, 3.1)
        _speed(speed, entries, theme, styles)
        legend(speed.get_legend_handles_labels()[0], 0.85, lower + 0.62, 2)

        heading(5.25, lower, "Where each checker is strong",
                "Solved, in % of each collection's tasks with a label (and how many)")  # fmt: skip
        collections = axes(7.35, plot, width - 7.35 - 0.3, 3.1)
        _collections(collections, entries, theme)

        text(0.3, height - 0.32, caption, fontsize=8.5, color=theme.muted)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, format=path.suffix[1:], metadata={"Date": None, "Creator": None}
                    if path.suffix == ".svg" else None, dpi=150)  # fmt: skip
        plt.close(fig)


# --------------------------------------------------------------------------- the words


def _outcome_table(entries: Sequence[Entry], keep: Callable[[Result], bool] | None) -> str:
    """How the tasks with a label ended, among those that ``keep`` lets through."""
    rows = []
    for entry in entries:
        counts = entry.counts(lambda r: has_label(r) and (keep is None or keep(r)))
        rows.append(
            [
                entry.name,
                share(counts["correct"], counts.total()),
                *(count(counts[kind]) for kind in LABELLED),
            ]
        )
    return table(["Checker", "Solved", *(OUTCOME_NAMES[kind] for kind in LABELLED)], rows)


def _unlabelled_table(entries: Sequence[Entry]) -> str:
    """How the tasks without a label ended, and what the answers were."""
    rows = []
    for entry in entries:
        results = entry.unlabelled()
        counts = entry.counts(lambda r: not has_label(r))
        rows.append(
            [
                entry.name,
                share(counts["unlabelled"], len(results)),
                *(count(sum(1 for r in results if r.answer == answer)) for answer in ("yes", "no")),
                *(count(counts[kind]) for kind in UNLABELLED[1:]),
            ]
        )
    headers = [
        "Checker",
        "Answered",
        "Yes",
        "No",
        *(OUTCOME_NAMES[kind] for kind in UNLABELLED[1:]),
    ]
    return table(headers, rows)


def _time_table(entries: Sequence[Entry]) -> str:
    rows = []
    for entry in entries:
        seconds = entry.solved_seconds()
        rows.append(
            [
                entry.name,
                share(len(seconds), len(entry.labelled())),
                duration(seconds[len(seconds) // 2] if seconds else None),
                duration(entry.seconds_to_solve(0.5)),
                duration(entry.seconds_to_solve(0.9)),
                duration(seconds[-1] if seconds else None),
                duration(entry.run.seconds),
            ]
        )
    headers = ["Checker", "Solved", "Median solved task", "Fastest 50% within",
               "Fastest 90% within", "Slowest solved task", "Whole run"]  # fmt: skip
    return table(headers, rows)


def _collection_table(entries: Sequence[Entry]) -> str:
    by_entry = [entry.collections() for entry in entries]
    rows = [
        [f"`{name}`", count(by_entry[0][name][1]), *(share(*solved[name]) for solved in by_entry)]
        for name in by_entry[0]
    ]
    return table(["Collection", "With a label", *(entry.name for entry in entries)], rows)


def _silence_table(entries: Sequence[Entry]) -> str:
    kinds = {
        "unknown": "Declined",
        "unsupported": "Not asked",
        "error": "Failed",
        "crash": "Crashed",
        "timeout": "Timed out",
    }
    rows = [
        [entry.name, *(count(sum(1 for r in entry.results if r.answer == kind)) for kind in kinds)]
        for entry in entries
    ]
    return table(["Checker", *kinds.values()], rows)


def _setup_table(entries: Sequence[Entry]) -> str:
    lines = ["| Checker | Version | Reads | Source |", "| --- | --- | --- | --- |"]
    for entry in entries:
        run = entry.run
        dialect = "draft 2020-12" if run.dialect == "2020-12" else run.dialect
        lines.append(f"| {entry.name} | {run.version} | {dialect} | <{run.homepage}> |")
    return "\n".join(lines)


def _scope(entries: Sequence[Entry], all_tasks: int) -> str:
    """Which tasks the runs cover, in words."""
    tasks = len(entries[0].results)
    if tasks == all_tasks:
        return f"all {count(tasks)} tasks"
    return f"a sample of {count(tasks)} of the {count(all_tasks)} tasks"


def markdown(entries: Sequence[Entry], with_format: frozenset[str], all_tasks: int) -> str:
    """The report, as the text of ``report.md``."""
    first = entries[0].run
    tasks = entries[0].results
    labelled = entries[0].labelled()
    formatted = sum(1 for r in labelled if r.case in with_format)
    agreement = [
        f"- {a.first} and {a.second} gave the same answer on {count(a.same)} of {count(a.tasks)} "
        f"tasks."
        + (
            f" A timeout or a crash on one side accounts for {count(a.unstable)} of the "
            f"{count(a.tasks - a.same)} others."
            if a.same != a.tasks
            else ""
        )
        for a in agreements(entries)
    ]
    parts = [
        "# Comparison of inclusion checkers",
        f"Corpus `{first.corpus}`, {_scope(entries, all_tasks)}, of which "
        f"{count(len(labelled))} have a label. Each checker had {first.timeout:g} seconds per "
        f"task. Run on "
        f"{first.started[:10]} on {first.processor} ({first.platform}).",
        '<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="chart-dark.svg">\n'
        '  <img alt="How every task ended, how fast tasks are solved, and the solved share by '
        'collection, for each checker" src="chart-light.svg">\n</picture>',
        "A task asks whether one schema accepts every instance valid under another. Every case "
        "is two tasks, one in each direction, and the corpus has a label for some of them. A "
        "task is **solved** when the checker gave the answer that the label gives, so only a "
        "task with a label can be solved, and every share of solved tasks is a share of the "
        "tasks with a label. A checker that declines is never wrong; a checker that can only "
        "say yes or no is wrong wherever its no meets a label that says yes.",
        "## Outcomes",
        f"The {count(len(labelled))} tasks with a label:",
        _outcome_table(entries, None),
        "- **Correct**: the answer is the label.\n"
        "- **Wrong no**: the checker said no where the label says that A subsumes B.\n"
        "- **Wrong yes**: the checker said yes where the label says that it does not.\n"
        "- **No answer**: the checker declined, failed, or cannot read the schemas.\n"
        "- **Timed out**: no answer within the time.",
        "### Without a label",
        f"The {count(len(tasks) - len(labelled))} tasks without a label. An answer to one can be "
        "held against nothing, so it is counted and not scored: a checker that always answers "
        "has answered them all.",
        _unlabelled_table(entries),
        "### With and without `format`",
        "The labels hold with `format` asserted. A checker that treats `format` as an "
        "annotation, or does not know it, answers a different question on the tasks that use "
        "it, so the counts of the tasks with a label follow for the two kinds of task.",
        f"The {count(len(labelled) - formatted)} whose schemas do not use `format`:",
        _outcome_table(entries, lambda r: r.case not in with_format),
        f"The {count(formatted)} whose schemas use `format`:",
        _outcome_table(entries, lambda r: r.case in with_format),
        "## Time",
        _time_table(entries),
        "The time of a task is measured inside the checker's process, from the two schemas as "
        f"text to the answer, after {first.warmup} unmeasured tasks to warm up. Reading the "
        "files, starting the process and rewriting a schema for an older draft are not in it. "
        "The fastest 50% is the time within which a checker solved half of the tasks with a "
        f"label; a share that it did not reach has no time ({NOTHING}).",
        "## Collections",
        "The share of each collection's tasks with a label that a checker solved.",
        _collection_table(entries),
        "## Where no answer came",
        "Among all tasks, with a label and without:",
        _silence_table(entries),
        "- **Declined**: the checker ran and said that it does not know.\n"
        "- **Not asked**: the checker reads an older draft, and that draft cannot express one "
        "of the schemas.\n"
        "- **Failed**: the checker raised an error or rejected a schema.\n"
        "- **Crashed**: the checker's process died.",
        *(["## Variants", "\n".join(agreement)] if agreement else []),
        "## What ran",
        _setup_table(entries),
        "- **Older drafts.** A checker that does not read draft 2020-12 gets every schema "
        "rewritten to its draft, with references resolved and keywords renamed. Nothing is "
        "encoded by other means: where the older draft lacks a keyword, the checker is not "
        "asked.\n"
        "- **Labels.** Most labels of five collections come from the witness generator that "
        "RWG succeeds, so they favour RWG by construction.\n"
        "- **subsumes.** subsumes is by the author of the corpus and is developed against it, "
        "so it does not meet these tasks for the first time as the other checkers do.\n"
        "- **Duplicates.** `synthesized` largely repeats `json-schema-test-suite`, so the two "
        "should not be read as independent evidence.",
    ]
    return "\n\n".join(parts) + "\n"


def readme_block(entries: Sequence[Entry], all_tasks: int, folder: str) -> str:
    """What the README shows of a report: the chart, the headline numbers and a link."""
    first = entries[0].run
    rows = []
    for entry in entries:
        counts = entry.counts()
        rows.append(
            [
                entry.name,
                entry.run.version,
                share(entry.solved(), len(entry.labelled())),
                count(counts["wrong_yes"]),
                count(counts["wrong_no"]),
                duration(entry.seconds_to_solve(0.5)),
                duration(entry.seconds_to_solve(0.9)),
            ]
        )
    headers = ["Checker", "Version", "Solved", "Wrong yes", "Wrong no",
               "Fastest 50% within", "Fastest 90% within"]  # fmt: skip
    return "\n\n".join(
        [
            f'<picture>\n  <source media="(prefers-color-scheme: dark)" '
            f'srcset="{folder}/{CHART_FILES["dark"]}">\n  <img alt="How every task ended, how '
            f'fast tasks are solved, and the solved share by collection, for each checker" '
            f'src="{folder}/{CHART_FILES["light"]}">\n</picture>',
            table(headers, rows),
            f"Measured on corpus `{first.corpus}`, {_scope(entries, all_tasks)}, of which "
            f"{count(len(entries[0].labelled()))} have a label, with {first.timeout:g} seconds "
            f"per task. [The full report]({folder}/{REPORT_FILE}) has the counts with and "
            f"without `format`, the tasks without a label, the collections and how it was "
            f"measured.",
        ]
    )


def update_readme(readme: Path, block: str) -> None:
    """Replace what lies between the two marker lines of the README."""
    text = readme.read_text(encoding="utf-8")
    if text.count(README_START) != 1 or text.count(README_END) != 1:
        raise ValueError(f"{readme} does not have the two comparison markers once each")
    before, rest = text.split(README_START)
    after = rest.split(README_END)[1]
    readme.write_text(f"{before}{README_START}\n\n{block}\n\n{README_END}{after}", encoding="utf-8")


def report(results: Path, out: Path, corpus: Path, readme: Path | None = None) -> None:
    """Write ``report.md`` and the two charts for the runs under ``results``.

    Args:
        results: A folder with one folder per checker, as ``run`` writes them.
        out: The folder for the report.
        corpus: The corpus the runs were over, for what the file of a case says about it.
        readme: A README whose marked part is to show the report, if any.
    """
    entries = read_entries(results)
    first = entries[0].run
    all_tasks = len(read_tasks(corpus))
    caption = (
        f"Corpus {first.corpus}, {_scope(entries, all_tasks)}, {first.timeout:g} s per task. "
        f"Solved: the answer is the label. Times are measured inside each checker's process."
    )
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        draw(entries, theme, caption, out / CHART_FILES[name])
    text = markdown(entries, cases_using(corpus, "format"), all_tasks)
    (out / REPORT_FILE).write_text(text, encoding="utf-8")
    if readme is not None:
        update_readme(readme, readme_block(entries, all_tasks, out.name))
