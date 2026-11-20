"""Puts a Markdown file into README.md as one of the parts that are written from data.

    uv run scripts/readme_part.py <part> <file>
    <command> | uv run scripts/readme_part.py <part>

A part lies between the two lines ``<!-- <part>:start -->`` and ``<!-- <part>:end -->``. What
is between them is replaced by the file, or by the standard input where no file is named, with
an empty line on either side. The rest of the README stays as it is. The script fails, and
changes nothing, when there is nothing to put there or when the README does not have each of
the two lines exactly once, the first before the second.

It uses the standard library only, so it runs without the project around it.
"""

import sys
from pathlib import Path

README = Path("README.md")


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: readme_part.py <part> [<file>]")
    part = sys.argv[1]
    given = Path(sys.argv[2]).read_bytes() if len(sys.argv) == 3 else sys.stdin.buffer.read()
    block = given.decode("utf-8").strip("\n")
    if not block:
        sys.exit(f"there is nothing to put into the part {part}")
    start, end = f"<!-- {part}:start -->", f"<!-- {part}:end -->"
    lines = README.read_text(encoding="utf-8").split("\n")
    if lines.count(start) != 1 or lines.count(end) != 1 or lines.index(end) < lines.index(start):
        sys.exit(f"{README} does not have the lines '{start}' and '{end}' once each, in that order")
    before, after = lines[: lines.index(start) + 1], lines[lines.index(end) :]
    README.write_text("\n".join([*before, "", block, "", *after]), encoding="utf-8")


if __name__ == "__main__":
    main()
