"""Reporting on a set of runs: a plot for light and dark pages, and a table.

The plot shows how fast each checker solves the tasks, and the table has a row for each
checker with what it solved, where it was wrong and how fast it was. The plot is drawn with
matplotlib, which the ``report`` extra brings; a run does not need it.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib as mpl
from matplotlib import pyplot as plt

from subsumes_benchmark import readme
from subsumes_benchmark.compare.summary import Entry, read_entries
from subsumes_benchmark.compare.words import count, duration, share, table

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from matplotlib.axes import Axes

CHART_FILES = {"light": "chart-light.svg", "dark": "chart-dark.svg"}

LINE_STYLES = ("solid", (0, (4, 2)), (0, (1, 2)))
# How many steps a curve of the plot keeps; more would only make the file larger.
STEPS = 250
# How many checkers the legend names in a row.
LEGEND_COLUMNS = 3


@dataclass(frozen=True)
class Theme:
    """The colours of the plot on one kind of page."""

    surface: str
    ink: str
    secondary: str
    muted: str
    grid: str
    axis: str
    # One per checker label, in the order the labels are listed; never cycled.
    series: Sequence[str]


LIGHT = Theme(
    surface="#fcfcfb",
    ink="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
)
DARK = Theme(
    surface="#1a1a19",
    ink="#f0efec",
    secondary="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    series=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"),
)
THEMES: Mapping[str, Theme] = {"light": LIGHT, "dark": DARK}


# --------------------------------------------------------------------------- the plot


def _bare(ax: Axes) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)


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


def draw(entries: Sequence[Entry], theme: Theme, caption: str, path: Path) -> None:
    """Draw the plot of a report: how fast each checker solves the tasks.

    The file is an SVG, or what the suffix of ``path`` names.
    """
    labels = list(dict.fromkeys(entry.run.checker.label for entry in entries))
    if len(labels) > len(theme.series):
        raise ValueError(
            f"the plot has colours for {len(theme.series)} checkers, not {len(labels)}"
        )
    # A colour per label and a line per variant, so that variants of a checker look alike.
    styles: dict[str, tuple] = {}
    for label, colour in zip(labels, theme.series, strict=False):
        variants = [entry for entry in entries if entry.run.checker.label == label]
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
    # Everything is placed in inches from the top left corner, so that a plot of more
    # checkers grows downwards and nothing else moves.
    width = 8.5
    legend = 0.95  # where the legend starts
    plot = legend + 0.24 * math.ceil(len(entries) / LEGEND_COLUMNS) + 0.25
    tall = 3.6
    height = plot + tall + 1.15
    with mpl.rc_context(settings):  # ty: ignore[invalid-argument-type]
        fig = plt.figure(figsize=(width, height))

        def text(left: float, top: float, words: str, **style: object) -> None:
            fig.text(left / width, 1 - top / height, words, va="top", **style)  # ty: ignore[invalid-argument-type]

        text(0.3, 0.3, "How fast the tasks are solved", fontsize=12, fontweight="bold",
             color=theme.ink)  # fmt: skip
        text(0.3, 0.57, "Share of the tasks with a label solved within a time", fontsize=9.5,
             color=theme.secondary)  # fmt: skip
        speed = fig.add_axes(
            (0.85 / width, 1 - (plot + tall) / height, (width - 0.85 - 0.4) / width, tall / height)
        )
        _speed(speed, entries, theme, styles)
        fig.legend(handles=speed.get_legend_handles_labels()[0], loc="upper left",
                   ncol=LEGEND_COLUMNS, frameon=False,
                   bbox_to_anchor=(0.85 / width, 1 - legend / height), fontsize=9,
                   labelcolor=theme.secondary, handlelength=2.2, handleheight=1.0,
                   columnspacing=1.6, handletextpad=0.6, borderpad=0, borderaxespad=0)  # fmt: skip
        text(0.3, height - 0.32, caption, fontsize=8.5, color=theme.muted)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, format=path.suffix[1:], metadata={"Date": None, "Creator": None}
                    if path.suffix == ".svg" else None, dpi=150)  # fmt: skip
        plt.close(fig)


# --------------------------------------------------------------------------- the table


def _linked(entry: Entry) -> str:
    """The name of a checker as a link to where it lives."""
    return f"[{entry.name}]({entry.run.checker.homepage})"


def block(entries: Sequence[Entry]) -> str:
    """What a README shows of the runs: a row for every checker, and what they ran on."""
    first = entries[0]
    rows = []
    for entry in entries:
        counts = entry.counts()
        rows.append(
            [
                _linked(entry),
                entry.run.checker.version,
                share(entry.solved(), len(entry.labelled())),
                count(counts["wrong_yes"]),
                count(counts["wrong_no"]),
                duration(entry.seconds_to_solve(0.5)),
                duration(entry.seconds_to_solve(0.9)),
            ]
        )
    headers = ["Checker", "Version", "Solved", "Wrong yes", "Wrong no",
               "Fastest 50% within", "Fastest 90% within"]  # fmt: skip
    scope = (
        f"Measured on corpus `{first.run.corpus}`: {count(len(first.results))} tasks, of which "
        f"{count(len(first.labelled()))} have a label, with {first.run.timeout:g} seconds per "
        f"task."
    )
    return f"{table(headers, rows)}\n\n{scope}"


def report(results: Path, out: Path, page: Path | None = None) -> str:
    """Draw the two plots for the runs under ``results`` and give the table of the checkers.

    Args:
        results: A folder with one folder per checker, as ``run`` wrote them.
        out: The folder for the plots.
        page: A README whose ``comparison`` part is to be the table, if any.

    Returns:
        The table and the line on what the checkers ran on, as Markdown.
    """
    entries = read_entries(results)
    first = entries[0].run
    caption = (
        f"Corpus {first.corpus}, {count(len(entries[0].results))} tasks, {first.timeout:g} s per "
        f"task. Solved: the answer is the label. Times are measured inside each checker's process."
    )
    out.mkdir(parents=True, exist_ok=True)
    for name, theme in THEMES.items():
        draw(entries, theme, caption, out / CHART_FILES[name])
    text = block(entries)
    if page is not None:
        readme.update(page, "comparison", text)
    return text
