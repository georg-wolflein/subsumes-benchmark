"""Words and numbers as a report writes them."""

from collections.abc import Sequence

NOTHING = "—"


def count(n: int) -> str:
    return f"{n:,}"


def plural(n: int, noun: str) -> str:
    """``1 task`` or ``1,234 tasks``."""
    return f"{count(n)} {noun}" if n == 1 else f"{count(n)} {noun}s"


def share(part: int, whole: int) -> str:
    """A share as a percentage. A share that is not zero never reads as zero."""
    if not whole:
        return NOTHING
    text = f"{100 * part / whole:.1f}%"
    return "<0.1%" if part and text == "0.0%" else text


def bold(text: str) -> str:
    return f"**{text}**"


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
