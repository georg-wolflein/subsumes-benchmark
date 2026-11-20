"""Puts Markdown into README.md as one of the parts that are written from data.

    uv run scripts/readme_part.py <part> <file>
    <command> | uv run scripts/readme_part.py <part>

A part lies between the two markers ``<!-- <part>:start -->`` and ``<!-- <part>:end -->``.
What is between them is replaced by the file, or by the standard input where no file is
named. The rest of the README stays as it is.

Where the first marker ends its line, the part is a block, such as a table: it is set off
from both markers by an empty line. Elsewhere the part stands within a sentence, such as a
number: it follows the first marker directly and has to be one line.

The script fails, and changes nothing, when there is nothing to put there, when the README
does not have each of the two markers exactly once, the first before the second, and when
more than one line is to go within a sentence.

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
    content = given.decode("utf-8").strip("\n")
    if not content:
        sys.exit(f"there is nothing to put into the part {part}")
    start, end = f"<!-- {part}:start -->", f"<!-- {part}:end -->"
    text = README.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1 or text.index(end) < text.index(start):
        sys.exit(f"{README} does not have '{start}' and '{end}' once each, in that order")
    before, rest = text.split(start)
    old, after = rest.split(end)
    if old.startswith("\n"):
        content = f"\n\n{content}\n\n"
    elif "\n" in content:
        sys.exit(f"the part {part} stands within a sentence, and more than one line is given")
    README.write_text(f"{before}{start}{content}{end}{after}", encoding="utf-8")


if __name__ == "__main__":
    main()
