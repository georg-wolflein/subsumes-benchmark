"""Reporting on a set of runs: a comparison as JSON, a plot for light and dark pages, and a table.

The comparison holds as much of the runs as a report shows, and the plot and the table are
made from it alone, so that both can be made again from the file. The plot shows how fast
each checker solves the tasks, with one curve per checker, and the table has a row for each
run with what it solved, where it was wrong and how fast it was. Each is a file of its own,
so that a page can show them where it likes. The plot is drawn with matplotlib, which the
``report`` extra brings; a run does not need it.
"""

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

import matplotlib as mpl
from matplotlib import pyplot as plt

from subsumes_benchmark.compare.summary import THOUSANDTHS, Comparison, read_entries
from subsumes_benchmark.compare.words import NOTHING, bold, duration, share, table

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from matplotlib.axes import Axes

    from subsumes_benchmark.generated.comparison import ComparedRun

CHART_FILES = {"light": "chart-light.svg", "dark": "chart-dark.svg"}
# The table of the checkers, as Markdown.
TABLE_FILE = "results.md"
# The comparison, as JSON: ``schemas/comparison.schema.json`` says what it holds.
COMPARISON_FILE = "comparison.json"

# How many steps a curve of the plot keeps; more would only make the file larger.
STEPS = 250
# The least distance between the names of two checkers at the right of the plot, in inches.
NAME_GAP = 0.19


@dataclass(frozen=True)
class Theme:
    """The colours of the plot on one kind of page."""

    surface: str
    ink: str
    secondary: str
    muted: str
    grid: str
    axis: str
    # One per checker, in the order that ``read_entries`` gives; never cycled.
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


def _thinned(seconds: Sequence[float]) -> tuple[list[float], list[float]]:
    """The steps of the curve of a run, a few hundred of them: the times and the shares."""
    stride = max(1, len(seconds) // STEPS)
    kept = sorted({*range(stride - 1, len(seconds), stride), len(seconds) - 1} - {-1})
    return [seconds[i] for i in kept], [(i + 1) / THOUSANDTHS for i in kept]


def _solved(run: ComparedRun, comparison: Comparison) -> float:
    """The share of the tasks with a label that a run solved."""
    # Nothing is solved where nothing has a label.
    return run.outcomes.correct / (comparison.labelled_tasks or 1)


def _speed(ax: Axes, runs: Sequence[ComparedRun], comparison: Comparison, theme: Theme) -> None:
    """For every run, the share of the tasks with a label it solved within a time."""
    timeout = comparison.timeout
    # The axis starts at the power of ten below all but the very fastest tasks.
    early = min(
        (seconds[len(seconds) // 100] for run in runs if (seconds := run.seconds_to_solve)),
        default=timeout / 10,
    )
    lowest = 10.0**-6
    while lowest * 10 <= early:
        lowest *= 10
    for run, colour in zip(runs, theme.series, strict=False):
        xs, ys = _thinned([max(s, lowest) for s in run.seconds_to_solve])
        ax.step([lowest, *xs, timeout], [0.0, *ys, _solved(run, comparison)], where="post",
                color=colour, lw=2)  # fmt: skip
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
    ax.set_ylabel("correctly solved tasks", color=theme.secondary, fontsize=9.5,
                  labelpad=8)  # fmt: skip


def _apart(wanted: Sequence[float], gap: float) -> list[float]:
    """Heights between 0 and 1 as close to the wanted ones as they get while ``gap`` apart.

    Heights that are too close move apart together, around their middle, so that each stays
    near where it is wanted. Of equal ones, the earlier is the higher.
    """
    order = sorted(range(len(wanted)), key=lambda i: (wanted[i], -i))
    # Each group is the heights that have to be placed together, lowest first.
    groups = [[i] for i in order]

    def span(group: Sequence[int]) -> tuple[float, float]:
        half = gap * (len(group) - 1) / 2
        middle = sum(wanted[i] for i in group) / len(group)
        middle = min(max(middle, half), max(1 - half, half))
        return middle - half, middle + half

    merged = True
    while merged:
        merged = False
        for lower, upper in pairwise(groups):
            if span(lower)[1] + gap > span(upper)[0] + 1e-9:
                lower.extend(upper)
                groups.remove(upper)
                merged = True
                break
    heights = [0.0] * len(wanted)
    for group in groups:
        lowest = span(group)[0]
        for place, i in enumerate(group):
            heights[i] = lowest + gap * place
    return heights


def draw(comparison: Comparison, theme: Theme, path: Path) -> None:
    """Draw the plot of a report: how fast each checker solves the tasks.

    A checker has one curve, that of the variant that solved most, since the variants of a
    checker differ in how they are called and hardly in what they solve; the table has a row
    for each. A curve is named at its right end, with the share of the tasks it solved, and
    the name with the highest share is bold. The file is an SVG, or what the suffix of
    ``path`` names.
    """
    checkers: dict[str, ComparedRun] = {}
    for run in comparison.runs:
        best = checkers.setdefault(run.checker.label, run)
        if run.outcomes.correct > best.outcomes.correct:
            checkers[run.checker.label] = run
    drawn = list(checkers.values())
    if len(drawn) > len(theme.series):
        raise ValueError(f"the plot has colours for {len(theme.series)} checkers, not {len(drawn)}")
    shares = [share(run.outcomes.correct, comparison.labelled_tasks) for run in drawn]
    names = [f"{label}  {solved}" for label, solved in zip(checkers, shares, strict=True)]
    # The best is whoever shows the share of the checker that solved most.
    highest = shares[max(range(len(drawn)), key=lambda i: drawn[i].outcomes.correct)]
    weights = ["bold" if solved == highest else "normal" for solved in shares]

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
    # Everything is placed in inches. The names stand to the right of the plot, so the
    # longest of them decides how wide the plot is; a letter is taken to be this wide.
    width, height = 8.5, 4.6
    left, top, bottom = 0.95, 0.25, 0.8
    space, letter = 0.12, 0.068
    right = space + letter * max(len(name) for name in names) + 0.15
    wide, tall = width - left - right, height - top - bottom
    with mpl.rc_context(settings):  # ty: ignore[invalid-argument-type]
        fig = plt.figure(figsize=(width, height))
        speed = fig.add_axes((left / width, bottom / height, wide / width, tall / height))
        _speed(speed, drawn, comparison, theme)
        # A dot marks where a curve ends, and its name stands next to the dot, or as close
        # to it as the other names leave room. Both are placed in the coordinates of the
        # plot, where 1 is its right edge.
        ends = [_solved(run, comparison) for run in drawn]
        heights = _apart(ends, NAME_GAP / tall)
        across = speed.transAxes
        named = zip(names, weights, theme.series, ends, heights, strict=False)
        for name, weight, colour, end, at in named:
            speed.plot([1], [end], marker="o", ms=4.5, color=colour, zorder=3,
                       transform=across, clip_on=False)  # fmt: skip
            speed.text(1 + space / wide, at, name, va="center", fontsize=9, color=theme.ink,
                       fontweight=weight, transform=across)  # fmt: skip
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, format=path.suffix[1:], metadata={"Date": None, "Creator": None}
                    if path.suffix == ".svg" else None, dpi=150)  # fmt: skip
        plt.close(fig)


# --------------------------------------------------------------------------- the table


def _linked(run: ComparedRun) -> str:
    """The name of a checker, with its variant, as a link to where it lives."""
    checker = run.checker
    name = checker.label if checker.variant is None else f"{checker.label} ({checker.variant})"
    return f"[{name}]({checker.homepage})"


def _within(run: ComparedRun, thousandths: int) -> float | None:
    """The time within which a run solved so many thousandths of the labelled tasks, if it did."""
    times = run.seconds_to_solve
    return times[thousandths - 1] if thousandths <= len(times) else None


def _marked[T: (int, float)](
    values: Sequence[T | None], words: Callable[[T], str], best: Callable[[Sequence[T]], T]
) -> list[str]:
    """A column of the table, with the best of its values in bold.

    Every cell that reads as the best one does is bold, so that two checkers that the table
    shows the same number for are marked alike.
    """
    cells = [NOTHING if value is None else words(value) for value in values]
    known = [value for value in values if value is not None]
    if not known:
        return cells
    winner = words(best(known))
    return [bold(cell) if cell == winner else cell for cell in cells]


def block(comparison: Comparison) -> str:
    """The table of the runs: a row for every run, the one that solved most first.

    Runs that solved equally many keep the order they came in. A correct result is a task
    that the checker solved and an incorrect one an answer that is wrong, both as a share of
    the tasks with a label. The best value of every column is bold: the most correct results,
    the fewest incorrect ones and the shortest times.
    """
    ranked = sorted(comparison.runs, key=lambda run: -run.outcomes.correct)

    def of_labelled(part: int) -> str:
        return share(part, comparison.labelled_tasks)

    wrong = [run.outcomes.wrong_yes + run.outcomes.wrong_no for run in ranked]
    columns = [
        [_linked(run) for run in ranked],
        [run.checker.version for run in ranked],
        _marked([run.outcomes.correct for run in ranked], of_labelled, max),
        _marked(wrong, of_labelled, min),
        _marked([_within(run, 500) for run in ranked], duration, min),
        _marked([_within(run, 900) for run in ranked], duration, min),
    ]
    headers = ["Checker", "Version", "Correct results", "Incorrect results",
               "Fastest 50% within", "Fastest 90% within"]  # fmt: skip
    return table(headers, [list(row) for row in zip(*columns, strict=True)])


def report(source: Path, out: Path) -> str:
    """Write the report on some runs: their comparison, the two plots and the table.

    Args:
        source: A folder with one folder per checker, as ``run`` wrote them, or the
            ``comparison.json`` of an earlier report, which the plots and the table are
            then made from again.
        out: The folder for the files of the report.

    Returns:
        The table and a line on what the checkers ran on, as Markdown.

    Raises:
        ReportError: The folder holds no runs, or runs that are not over the same tasks.
        ConfigError: The file is not what the schema of a comparison says.
    """
    out.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        comparison = Comparison.of(read_entries(source))
        comparison.write(out / COMPARISON_FILE)
    else:
        comparison = Comparison.read(source)
    for name, theme in THEMES.items():
        draw(comparison, theme, out / CHART_FILES[name])
    text = block(comparison)
    (out / TABLE_FILE).write_text(f"{text}\n", encoding="utf-8")
    return f"{text}\n\n{comparison.line()}"
